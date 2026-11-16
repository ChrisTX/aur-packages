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
