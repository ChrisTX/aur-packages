"""Publishing to the AUR: push and its records, adopt, publish; against local repositories."""

import subprocess
from pathlib import Path

import pytest

from aur_packages import aur
from aur_packages.repo import Checkout, SelectionError


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def srcinfo(name: str, desc: str = "A package") -> str:
    return f"pkgbase = {name}\n\tpkgdesc = {desc}\n\tpkgver = 1\n\tpkgrel = 1\n\npkgname = {name}\n"


def add_package(root: Path, folder: str) -> None:
    (root / folder).mkdir(parents=True)
    (root / folder / ".SRCINFO").write_text(srcinfo(folder.split("/")[-1]))
    (root / folder / "PKGBUILD").write_text("# Maintainer: Us <us at example dot org>\npkgname=x\n")


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


README = """\
# Packages

### Other

| Package | Description | Version |
| --- | --- | --- |
| [alpha](https://aur.archlinux.org/packages/alpha) | A package | x |
| [gamma](https://aur.archlinux.org/packages/gamma) | A package | x |

### Not on the AUR

| Package | Description | Why |
| --- | --- | --- |
| [beta](local/beta) | A package | testing |
"""


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Checkout:
    """A repository with alpha at the top level and beta in local/, and an empty fake AUR."""
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "master")
    for key, value in (("user.name", "Us"), ("user.email", "us@example.org"), ("commit.gpgsign", "false")):
        git(root, "config", key, value)
    add_package(root, "alpha")
    add_package(root, "local/beta")
    (root / "README.md").write_text(README)
    commit(root, "init")
    (tmp_path / "aur").mkdir()
    monkeypatch.setenv("AUR_PACKAGES_AUR", f"file://{tmp_path / 'aur'}")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.chdir(root)
    return Checkout(root, root)


def fake_aur(checkout: Checkout, base: str, *files: tuple[str, str]) -> str:
    """The AUR's repository of a package, with a commit of the files given (none: empty)."""
    bare = Path(str(checkout.root.parent / "aur" / f"{base}.git"))
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    if not files:
        return ""
    work = checkout.root.parent / f"aur-work-{base}"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True, capture_output=True)
    for key, value in (
        ("user.name", "Them"),
        ("user.email", "them@example.org"),
        ("commit.gpgsign", "false"),
    ):
        git(work, "config", key, value)
    for name, content in files:
        (work / name).write_text(content)
    commit(work, "Initial upload")
    git(work, "push", "-q", "origin", "HEAD:master")
    return git(work, "rev-parse", "HEAD")


def test_push_needed(checkout: Checkout) -> None:
    root = checkout.root
    assert aur.push_needed("alpha")
    git(root, "update-ref", aur.pushed_ref("alpha"), "HEAD")
    assert not aur.push_needed("alpha")
    # a commit elsewhere doesn't count, one of the package does
    (root / "README.md").write_text("changed\n")
    commit(root, "README.md: change it")
    assert not aur.push_needed("alpha")
    (root / "alpha" / "PKGBUILD").write_text("pkgname=y\n")
    commit(root, "alpha: change it")
    assert aur.push_needed("alpha")
    # a merge that joins a history to the package counts, although its files stay as they are
    git(root, "update-ref", aur.pushed_ref("alpha"), "HEAD")
    tree = git(root, "rev-parse", "HEAD^{tree}")
    other = git(root, "commit-tree", "-m", "other history", tree)
    joined = git(root, "commit-tree", "-p", "HEAD", "-p", other, "-m", "join\n\ngit-subtree-dir: alpha", tree)
    git(root, "merge", "-q", "--ff-only", joined)
    assert aur.push_needed("alpha")


@pytest.fixture
def aurpublish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in aurpublish on PATH that logs its calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "aurpublish.log"
    script = bin_dir / "aurpublish"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{__import__('os').environ['PATH']}")
    return log


def test_push(checkout: Checkout, aurpublish: Path, capsys: pytest.CaptureFixture[str]) -> None:
    add_package(checkout.root, "gamma")
    commit(checkout.root, "gamma: add it")
    assert aur.run_push(checkout, [], [], no_check=True, force=False, dry_run=True) == 0
    assert "Would check and push: alpha gamma" in capsys.readouterr().out
    assert not aurpublish.exists()
    assert aur.run_push(checkout, [], ["gamma"], no_check=True, force=False, dry_run=False) == 0
    assert aurpublish.read_text() == "alpha\n"
    assert git(checkout.root, "rev-parse", aur.pushed_ref("alpha")) == git(checkout.root, "rev-parse", "HEAD")
    assert aur.run_push(checkout, ["alpha"], [], no_check=True, force=False, dry_run=False) == 0
    assert "Nothing new since the last push of 1 package" in capsys.readouterr().out
    assert aurpublish.read_text() == "alpha\n"
    # the excluded package that isn't one is named, not the first
    with pytest.raises(SelectionError, match="Not a package: nope"):
        aur.run_push(checkout, [], ["gamma", "nope"], no_check=True, force=False, dry_run=False)


def test_adopt(
    checkout: Checkout, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    adopted: list[tuple[str, str]] = []
    monkeypatch.setattr(aur, "adopt_maintainers", lambda package, head: adopted.append((package, head)))
    head = fake_aur(checkout, "alpha", ("PKGBUILD", "pkgname=alpha\n"))
    assert aur.run_adopt(checkout, ["alpha"], dry_run=True) == 0
    assert "would merge the AUR's" in capsys.readouterr().out
    assert aur.run_adopt(checkout, ["alpha"], dry_run=False) == 0
    split = git(checkout.root, "subtree", "split", "-q", "-P", "alpha")
    git(checkout.root, "merge-base", "--is-ancestor", head, split)
    assert adopted == [("alpha", head)]
    # a second time, it's on top already
    assert aur.run_adopt(checkout, ["alpha"], dry_run=False) == 0
    assert "already on top of the AUR's" in capsys.readouterr().out


def test_publish(checkout: Checkout, capsys: pytest.CaptureFixture[str]) -> None:
    root = checkout.root
    (root / "local" / "beta" / "PKGBUILD").write_text("pkgname=beta\n")
    commit(root, "beta: change it")
    fake_aur(checkout, "beta")
    assert aur.run_publish(checkout, ["beta"], "Nope", adopt=False, dry_run=False) == 1
    assert aur.run_publish(checkout, ["beta"], "Other", adopt=False, dry_run=False) == 0
    assert "beta: moved out of local/ with a history of 2 commits" in capsys.readouterr().out
    assert (root / "beta" / "PKGBUILD").exists()
    assert not (root / "local" / "beta").exists()
    readme = (root / "README.md").read_text()
    # the row moves into the section's table, in order, and becomes the AUR's
    assert readme.index("[alpha]") < readme.index("[beta](https://aur.archlinux.org/packages/beta)")
    assert readme.index("[beta]") < readme.index("[gamma]")
    assert "(local/beta)" not in readme
    # the subtree push pushes has the package's commits, and starts at its first one in local/
    split = git(root, "subtree", "split", "-q", "-P", "beta")
    assert git(root, "rev-list", "--count", split) == "2"


def test_readme_move_row(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(README)
    aur.readme_move_row(readme, "beta", "Other", "| [beta](x) | B | y |")
    lines = readme.read_text().splitlines()
    assert lines[6:9] == [
        "| [alpha](https://aur.archlinux.org/packages/alpha) | A package | x |",
        "| [beta](x) | B | y |",
        "| [gamma](https://aur.archlinux.org/packages/gamma) | A package | x |",
    ]
    with pytest.raises(SelectionError):
        aur.readme_move_row(readme, "zeta", "Not on the AUR", "| [zeta](x) |")
