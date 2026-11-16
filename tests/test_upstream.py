"""The upstream references of the packages, read offline."""

from aur_packages import upstream
from aur_packages.srcinfo import Srcinfo
from aur_packages.upstream import Reference

PKGBUILD = """\
source=("git+https://github.com/owner/project.git#tag=1.0")
prepare() {
  # Backported (https://github.com/owner/project/pull/12, merged as owner/project@0e3f7dbc), see
  # also other/lib#7 and our issue #34: fixed upstream in other/lib@abcdef1; PR #12 again
  sed -i 's/#99//' file  # #56 of the package
  echo "${var#1}"
}
"""


def test_references() -> None:
    assert upstream.references(PKGBUILD, "owner/project") == [
        Reference("owner/project", number=12),
        Reference("owner/project", commit="0e3f7dbc"),
        Reference("other/lib", number=7),
        Reference("owner/project", number=34),
        Reference("other/lib", commit="abcdef1"),
        Reference("owner/project", number=56),
    ]
    # Without a repository of its own, bare numbers mean nothing
    assert Reference("owner/project", number=34) not in upstream.references(PKGBUILD, "")


def test_source() -> None:
    def parse(source: str) -> tuple[str, str]:
        return upstream.source(Srcinfo.parse(f"pkgbase = x\n\tsource = {source}\n"))

    assert parse("git+https://github.com/a/b.git#tag=1.13.0.7493") == ("a/b", "1.13.0.7493")
    assert parse("git+https://github.com/a/b.git#tag=2.1.10?signed") == ("a/b", "2.1.10")
    assert parse("b-1.tar.gz::https://github.com/a/b/archive/refs/tags/v7.6.10.tar.gz") == ("a/b", "v7.6.10")
    assert parse("b.tar.gz::https://github.com/a/b/archive/0123abc.tar.gz") == ("a/b", "0123abc")
    assert parse("https://example.org/b-1.tar.gz") == ("", "")


def test_final_keeps_what_cant_change() -> None:
    api = "https://api.github.com/repos/o/r"
    # An issue stays an issue, a pull request a pull request
    assert upstream.final(f"{api}/issues/1", {"state": "open", "body": "text"}) == {}
    assert upstream.final(f"{api}/issues/2", {"pull_request": {"url": "x"}}) == {"pull_request": {"url": "x"}}
    # Closed pull requests, merged or not, but not open ones
    merged = {"state": "closed", "merged": True, "merge_commit_sha": "abc", "draft": False, "title": "t"}
    assert upstream.final(f"{api}/pulls/2", merged) == {
        "state": "closed",
        "merged": True,
        "merge_commit_sha": "abc",
        "draft": False,
    }
    assert upstream.final(f"{api}/pulls/3", {"state": "open"}) is None
    # A tag or commit that contains a commit, but not one that doesn't (yet: it could be a branch)
    assert upstream.final(f"{api}/compare/abc...v1", {"status": "ahead", "files": []}) == {"status": "ahead"}
    assert upstream.final(f"{api}/compare/abc...v1", {"status": "behind"}) is None
    assert upstream.final(f"{api}/releases?per_page=1", [{"tag_name": "v1"}]) is None
