"""The upstream references of the packages, read offline."""

import pytest

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


DIRECTIVES = """\
prepare() {
  # A fix of upstream's
  # upstream: backport owner/project#12
  patch -Np1 -i "$srcdir/fix.patch"
  # upstream: pending #13 and other/lib@abcdef1
  patch -Np1 -d lib -i "$srcdir/lib.patch"
  # upstream: none, the system's zlib
  git -C sub apply "$srcdir/zlib.patch"
  # Not a directive above it
  patch -Np1 -i "$srcdir/bare.patch"
  # upstream: workaround
  # upstream: none
  # upstream: fixed owner/project#1
  patch -Np1 -i "$srcdir/broken.patch"

  # upstream: backport owner/project#14
  sed -i 's/a/b/' file
  # upstream: backport owner/project#15
  cd sub || exit
  patch -Np1 -i "$srcdir/far.patch"
}
"""


def test_directives() -> None:
    found, problems = upstream.directives(DIRECTIVES, "owner/project")
    assert [(d.line, d.verb, d.references) for d in found] == [
        (3, "backport", (Reference("owner/project", number=12),)),
        (5, "pending", (Reference("owner/project", number=13), Reference("other/lib", commit="abcdef1"))),
        (7, "none", ()),
        (16, "backport", (Reference("owner/project", number=14),)),
        (18, "backport", (Reference("owner/project", number=15),)),
    ]
    assert found[2].text == "the system's zlib"
    # The patch without a directive, the malformed ones, and a directive that isn't right above
    assert [line for line, _ in problems] == [10, 11, 12, 13, 20]
    assert "verb is one of" in problems[3][1]


def test_note() -> None:
    assert upstream.note("merged, in the packaged 1.0", True)
    assert upstream.note("commit, in the packaged 1.0", True)
    assert upstream.note("closed, not merged", False)
    assert upstream.note("issue closed (completed)", False)
    assert upstream.note("merged, not in the packaged 1.0, in 1.1", False) is None
    assert upstream.note("open", False) is None
    assert upstream.note("issue open", False) is None


def test_released_in_another_source(monkeypatch: pytest.MonkeyPatch) -> None:
    asked = []

    def contains(repository: str, commit: str, ref: str) -> bool:
        asked.append((repository, commit, ref))
        return True

    monkeypatch.setattr(upstream, "contains", contains)
    reference = Reference("other/lib", number=7)
    others = {"owner/project": "1.0", "Other/Lib": "v2.0"}
    # Its own source of the other repository, rather than a submodule of the package's
    assert upstream.released(reference, "abc", "owner/project", "1.0", others) == (
        "in the packaged v2.0",
        True,
    )
    assert asked == [("other/lib", "abc", "v2.0")]


def test_sources() -> None:
    srcinfo = Srcinfo.parse(
        "pkgbase = x\n"
        "\tsource = git+https://github.com/a/b.git#tag=1.0\n"
        "\tsource = git+https://github.com/c/d.git#commit=0123abc\n"
        "\tsource = git+https://github.com/e/f.git\n"
    )
    assert upstream.sources(srcinfo) == {"a/b": "1.0", "c/d": "0123abc", "e/f": ""}


def test_once_asks_once_in_parallel() -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor

    calls = []

    @upstream.once
    def lookup(url: str) -> str:
        calls.append(url)
        time.sleep(0.05)
        return url.upper()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lookup, ["a"] * 8 + ["b"]))
    assert results == ["A"] * 8 + ["B"]
    assert sorted(calls) == ["a", "b"]
    upstream.forget()
    assert lookup("a") == "A"
    assert calls.count("a") == 2


def test_once_passes_errors_on() -> None:
    @upstream.once
    def broken(url: str) -> str:
        raise ValueError(url)

    with pytest.raises(ValueError, match="x"):
        broken("x")
    # The failure is kept like an answer, until forget
    with pytest.raises(ValueError, match="x"):
        broken("x")
    upstream.forget()
