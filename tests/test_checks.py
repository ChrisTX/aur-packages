"""The checks of every commit: gitignore, quoting, pins, readme and sync, and the .SRCINFO they read."""

import shutil
from pathlib import Path

import pytest

from aur_packages import checks, pins
from aur_packages.repo import GITIGNORE, Checkout
from aur_packages.srcinfo import Srcinfo

SRCINFO = """\
pkgbase = split
\tpkgdesc = The split package
\tpkgver = 1.2
\tpkgrel = 3
\tepoch = 1

pkgname = split-tools
\tpkgdesc = Its tools

pkgname = split

pkgname = split-debug
"""


def package(root: Path, folder: str, srcinfo: str, pkgbuild: str = "") -> None:
    (root / folder).mkdir(parents=True)
    (root / folder / ".SRCINFO").write_text(srcinfo)
    (root / folder / "PKGBUILD").write_text(pkgbuild)


def single(name: str, desc: str = "A package") -> str:
    return f"pkgbase = {name}\n\tpkgdesc = {desc}\n\tpkgver = 1\n\tpkgrel = 1\n\npkgname = {name}\n"


def test_srcinfo() -> None:
    srcinfo = Srcinfo.parse(SRCINFO)
    assert srcinfo.pkgbase == "split"
    assert srcinfo.version() == "1:1.2-3"
    assert srcinfo.pkgdesc() == "The split package"
    # the package named like the pkgbase first, without debug packages
    assert srcinfo.pkgnames() == ["split", "split-tools"]
    # without a pkgdesc of the pkgbase, the one of the package named like it
    assert (
        Srcinfo.parse("pkgbase = a\n\npkgname = b\n\tpkgdesc = B\n\npkgname = a\n\tpkgdesc = A\n").pkgdesc()
        == "A"
    )


def parts(*types_and_values: tuple[str, str]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for kind, value in types_and_values:
        if kind == "DblQuoted":
            result.append({"Type": kind, "Parts": [{"Type": "Lit", "Value": value}]})
        else:
            result.append({"Type": kind, "Value": value})
    return result


def test_quoting_problem() -> None:
    problem = checks.quoting_problem
    assert problem(parts(("Lit", "glibc"))) is None
    assert problem(parts(("SglQuoted", "glibc"))) == "'glibc' is a plain word, write it unquoted"
    assert problem(parts(("SglQuoted", "git: for git sources"))) is None
    assert problem(parts(("DblQuoted", "bash"))) == '"bash" is a plain word, write it unquoted'
    assert problem(parts(("DblQuoted", "don't"))) is None
    assert (
        problem(parts(("DblQuoted", "two words"))) == '"two words" has nothing that expands, single-quote it'
    )
    assert (
        problem(parts(("Lit", "x"), ("SglQuoted", "y")))
        == "a word quoted in part, double-quote it as a whole"
    )
    expanding = [{"Type": "DblQuoted", "Parts": [{"Type": "ParamExp"}, {"Type": "Lit", "Value": "-bin"}]}]
    assert problem(expanding) is None


@pytest.mark.skipif(shutil.which("shfmt") is None, reason="needs shfmt")
def test_quoting_findings(tmp_path: Path) -> None:
    pkgbuild = tmp_path / "PKGBUILD"
    pkgbuild.write_text(
        "depends=('glibc' bash)\n"
        # an empty array has no elements, which crashed the jq program of the bash version
        "makedepends=()\n"
        'package_x() {\n  optdepends=("two words")\n}\n'
        "source=('not-checked')\n"
    )
    assert checks.quoting_findings(pkgbuild, "x/PKGBUILD") == [
        "x/PKGBUILD:1:10: depends: 'glibc' is a plain word, write it unquoted",
        'x/PKGBUILD:4:15: optdepends: "two words" has nothing that expands, single-quote it',
    ]


def test_pins(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    package(tmp_path, "good", single("good"), "pkgver=1.0.r3.g4b8b3d3\n_commit=4b8b3d3abcdef\n")
    package(tmp_path, "stale", single("stale"), "pkgver=1.0.r3.g4b8b3d3\n_commit='0123456789'\n")
    package(tmp_path, "plain", single("plain"), "pkgver=1.0\n_commit=0123456\n")
    checkout = Checkout(tmp_path, tmp_path)
    assert pins.run_pins(checkout, ["good", "plain/PKGBUILD"]) == 0
    assert pins.run_pins(checkout, []) == 1
    assert capsys.readouterr().out == (
        "stale/PKGBUILD: _commit 0123456789 isn't the commit pkgver names, 4b8b3d3: "
        "./aur-packages pins --update stale\n"
    )


def test_readme_row() -> None:
    srcinfo = Srcinfo.parse(SRCINFO)
    assert checks.readme_row(srcinfo, "split").startswith(
        "| [split](https://aur.archlinux.org/pkgbase/split) (`split`, `split-tools`) | The split package | "
    )
    assert checks.readme_row(srcinfo, "local/split") == "| [split](local/split) | The split package | "
    assert checks.readme_row(srcinfo, "overrides/split") == "| [split](overrides/split) | "


def test_readme(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    package(tmp_path, "one", single("one", "First"))
    package(tmp_path, "local/two", single("two", "Second"))
    checkout = Checkout(tmp_path, tmp_path)
    one = checks.readme_row(Srcinfo.parse(single("one", "First")), "one")
    (tmp_path / "README.md").write_text(f"{one}\n| [two](local/two) | Second | Why |\n")
    assert checks.run_readme(checkout) == 0
    (tmp_path / "README.md").write_text(f"{one}\n{one}\n| [ghost](local/ghost) | x |\n")
    assert checks.run_readme(checkout) == 1
    out = capsys.readouterr().out
    assert "more than one row for one" in out
    assert "no row for local/two, which should start with:\n  | [two](local/two) | Second | " in out
    assert "a row for ghost, which isn't a package" in out


def test_sync(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    template = tmp_path / "templates" / "package"
    template.mkdir(parents=True)
    for name in checks.TEMPLATE_FILES:
        (template / name).write_text(f"{name}\n\n")
    (tmp_path / "templates" / "root-hooks.yaml").write_text("root\n")
    package(tmp_path, "one", single("one"))
    package(tmp_path, "overrides/arch", single("arch"))
    checkout = Checkout(tmp_path, tmp_path)
    assert checks.run_sync(checkout, [], dry_run=True) == 1
    assert "Differs from the template: one/.typos.toml" in capsys.readouterr().err
    assert checks.run_sync(checkout, [], dry_run=False) == 0
    # trailing blank lines collapse to one newline, as $(cat …) did
    assert (tmp_path / "one" / ".typos.toml").read_text() == ".typos.toml\n"
    assert (tmp_path / ".pre-commit-config.yaml").read_text() == ".pre-commit-config.yaml\n\nroot\n"
    # overrides keep Arch Linux's files
    assert not (tmp_path / "overrides" / "arch" / ".typos.toml").exists()
    assert checks.run_sync(checkout, [], dry_run=True) == 0


def test_gitignore_missing() -> None:
    # The template with lines of the package's own, before its end comment as well as after it
    own = (
        GITIGNORE.replace("# End of", "# The source archive\n*.tar.gz\n\n# End of") + "\n# Git sources\nx/\n"
    )
    assert checks.gitignore_missing(own) == []
    # An AUR package's own .gitignore from before it came here
    assert checks.gitignore_missing("x*.tar.*\n\npkg\nsrc\n") == [
        "*.tar", "*.tar.*", "*.jar", "*.exe", "*.msi", "*.zip", "*.tgz", "*.log", "*.log.*", "*.sig", "pkg/", "src/",
    ]  # fmt: skip


def test_gitignore(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    package(tmp_path, "one", single("one"))
    package(tmp_path, "overrides/arch", single("arch"))
    checkout = Checkout(tmp_path, tmp_path)
    (tmp_path / "one" / ".gitignore").write_text(GITIGNORE.replace("*.log\n", ""))
    assert checks.run_gitignore(checkout, []) == 1
    err = capsys.readouterr().err
    assert "one/.gitignore lacks patterns of the archlinuxpackages template: *.log\n" in err
    # overrides/ get it from ./aur-packages overrides add, and are checked as well
    assert "overrides/arch/.gitignore is missing" in err
    (tmp_path / "one" / ".gitignore").write_text(GITIGNORE)
    (tmp_path / "overrides" / "arch" / ".gitignore").write_text(GITIGNORE)
    assert checks.run_gitignore(checkout, []) == 0
