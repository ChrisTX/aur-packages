"""The packages of overrides/: comparing with Arch Linux, adding, pulling and removing them."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from aur_packages import overrides
from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo


def git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def configure(root: Path) -> None:
    for key, value in (("user.name", "Us"), ("user.email", "us@example.org"), ("commit.gpgsign", "false")):
        git(root, "config", key, value)


PKGBUILD = """\
pkgname=tool
pkgver=1.0
pkgrel={rel}
source=("git+https://example.org/tool.git#tag=1.0" patch.diff)
"""
README = """\
| Package | Changes | Until |
| --- | --- | --- |
| [zed](overrides/zed) | x | y |
"""


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Checkout:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "master")
    configure(root)
    (root / "README.md").write_text(README)
    zed = root / "overrides" / "zed"
    zed.mkdir(parents=True)
    (zed / "PKGBUILD").write_text("pkgname=zed\n")
    (zed / ".SRCINFO").write_text("pkgbase = zed\n\tpkgver = 2\n\tpkgrel = 1.1\n\npkgname = zed\n")
    commit(root, "init")
    monkeypatch.chdir(root)
    return Checkout(root, root)


def test_status(
    checkout: Checkout, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for theirs, expected in ((("2-1", "extra"), 0), (("2-2", "core-testing"), 1), (None, 2)):
        monkeypatch.setattr(overrides, "arch_version", lambda base, value=theirs: value)
        assert overrides.override_status(checkout, "overrides/zed") == expected
    out = capsys.readouterr().out
    assert (
        "zed                            2-1.1, Arch Linux has 2-2 (core-testing): the override can go" in out
    )
    assert "not in Arch Linux's repositories" in out
    monkeypatch.setattr(overrides, "arch_version", lambda base: ("2-2", "core-testing"))
    assert overrides.run_check(checkout, []) == 1


def test_remove(checkout: Checkout, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(overrides, "arch_version", lambda base: ("2-1", "extra"))
    assert overrides.run_remove(checkout, ["zed"], force=False, dry_run=False) == 1
    assert (checkout.root / "overrides" / "zed").exists()
    monkeypatch.setattr(overrides, "arch_version", lambda base: ("2-2", "extra"))
    assert overrides.run_remove(checkout, ["zed"], force=False, dry_run=True) == 0
    assert (checkout.root / "overrides" / "zed").exists()
    assert overrides.run_remove(checkout, ["zed"], force=False, dry_run=False) == 0
    assert not (checkout.root / "overrides" / "zed").exists()
    assert "(overrides/zed)" not in (checkout.root / "README.md").read_text()
    assert git(checkout.root, "log", "-1", "--format=%s") == "overrides: drop zed, Arch Linux has 2-2"


def test_git_folders() -> None:
    srcinfo = Srcinfo.parse(
        "pkgbase = a\n\tsource = git+https://example.org/one.git#tag=1\n\tsource = two::git+https://x/y\n"
        "\tsource_x86_64 = git+https://example.org/three?signed\n\tsource = https://example.org/f.tar.gz\n"
    )
    assert overrides.git_folders(srcinfo) == ["one", "two", "three"]


def test_add_readme_row(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(README)
    overrides.add_readme_row(readme, "tool")
    assert readme.read_text().splitlines()[2].startswith("| [tool](overrides/tool) | TODO")


@pytest.mark.skipif(
    not Path("/usr/share/devtools/lib/api/gitlab.sh").exists() or shutil.which("makepkg") is None,
    reason="needs devtools and makepkg",
)
def test_add_and_pull(checkout: Checkout, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arch Linux's packaging of tool, in a fake GitLab group
    arch = tmp_path / "arch"
    packaging = arch / "tool"
    packaging.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(packaging)], check=True)
    configure(packaging)
    (packaging / "PKGBUILD").write_text(PKGBUILD.format(rel=3))
    srcinfo = subprocess.run(
        ["makepkg", "--printsrcinfo"], cwd=packaging, capture_output=True, text=True, check=True
    )
    (packaging / ".SRCINFO").write_text(srcinfo.stdout)
    (packaging / "REUSE.toml").write_text("version = 1\n")
    commit(packaging, "upgpkg: 1.0-3")
    shutil.move(str(packaging), str(arch / "tool.git.work"))
    subprocess.run(
        ["git", "clone", "-q", "--bare", str(arch / "tool.git.work"), str(arch / "tool.git")], check=True
    )
    monkeypatch.setenv("AUR_PACKAGES_ARCH", f"file://{arch}")
    # expac, which tells the pkgbase
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "expac").write_text("#!/bin/sh\necho tool\n")
    (bin_dir / "expac").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")

    assert overrides.run_add(checkout, "tool-docs", dry_run=False) == 0
    root = checkout.root
    assert git(root, "log", "-1", "--format=%s") == "overrides: add Arch Linux's tool packaging"
    folder = root / "overrides" / "tool"
    assert "pkgrel=3.1" in (folder / "PKGBUILD").read_text()
    assert Srcinfo.load(folder).version() == "1.0-3.1"
    assert (folder / ".gitignore").read_text().endswith("# Git sources\ntool/\n")
    assert 'path = ".gitignore"' in (folder / "REUSE.toml").read_text()
    assert "| [tool](overrides/tool) | TODO" in (root / "README.md").read_text()
    # an existing package isn't added again
    assert overrides.run_add(checkout, "tool", dry_run=False) == 1

    # committed, then Arch Linux's next release merges in
    commit(root, "upgpkg: tool 1.0-3.1")
    work = arch / "tool.git.work"
    git(work, "remote", "add", "origin", str(arch / "tool.git"))
    (work / "PKGBUILD").write_text(PKGBUILD.format(rel=3) + "# changed by Arch\n")
    commit(work, "upgpkg: 1.0-4")
    git(work, "push", "-q", "origin", "HEAD:main")
    assert overrides.run_pull(checkout, ["tool"], dry_run=False) == 0
    assert "# changed by Arch" in (folder / "PKGBUILD").read_text()
    assert "pkgrel=3.1" in (folder / "PKGBUILD").read_text()
