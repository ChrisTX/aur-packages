"""The git hooks: the summary of a commit message, filling it in, and installing the hooks."""

import shutil
import subprocess
from pathlib import Path

import pytest

from aur_packages import hooks
from aur_packages.repo import Checkout


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


def srcinfo(name: str, version: str) -> str:
    pkgver, pkgrel = version.split("-")
    return f"pkgbase = {name}\n\tpkgver = {pkgver}\n\tpkgrel = {pkgrel}\n\npkgname = {name}\n"


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Checkout:
    """A repository with a package at the top level, one in local/ and a file, committed."""
    git(tmp_path, "init", "-q")
    # the git of the test has to be the temporary repository's (see conftest.isolated_git)
    top = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert Path(top) == tmp_path.resolve()
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.org")
    git(tmp_path, "config", "commit.gpgsign", "false")
    for folder in ("one", "local/two"):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / ".SRCINFO").write_text(srcinfo(folder.split("/")[-1], "1.0-1"))
        (tmp_path / folder / "PKGBUILD").write_text("pkgname=x\n")
    (tmp_path / "README.md").write_text("readme\n")
    # British English, as the repository's .typos.toml has it
    (tmp_path / ".typos.toml").write_text('[default]\nlocale = "en-gb"\n')
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    monkeypatch.chdir(tmp_path)
    return Checkout(tmp_path, tmp_path)


def stage_version(checkout: Checkout, folder: str, version: str) -> None:
    (checkout.root / folder / ".SRCINFO").write_text(srcinfo(folder.split("/")[-1], version))
    git(checkout.root, "add", "-A")


def test_check_summary(checkout: Checkout) -> None:
    check = hooks.check_summary
    stage_version(checkout, "one", "1.1-1")
    assert check(checkout, "upgpkg: one 1.1-1") is None
    assert (
        check(checkout, "upgpkg: one 1.0-1")
        == "The version in the summary is 1.0-1, but one/.SRCINFO has 1.1-1"
    )
    assert check(checkout, "upgpkg: nope 1-1") == "Not a package with a staged .SRCINFO: nope"
    # packages by name, files and folders at the top level, also ones only HEAD has
    assert check(checkout, "two: fix it") is None
    assert check(checkout, "README.md: fix a typo") is None
    (checkout.root / "README.md").unlink()
    assert check(checkout, "README.md: drop it") is None
    assert (
        check(checkout, "nope: fix it")
        == "The scope 'nope' is neither a package nor a top-level file or folder"
    )
    assert check(checkout, "one: fix it.") == "The summary ends with a period: one: fix it."
    assert (check(checkout, "Fix it") or "").startswith("The summary has to be")


def test_exempt_summaries() -> None:
    for summary in ("Merge branch 'x'", "fixup! one: x", "Add 'one/' from commit 'abc'", "Squashed 'x'"):
        assert hooks.EXEMPT.match(summary), summary
    assert not hooks.EXEMPT.match("one: merge it")


@pytest.mark.skipif(shutil.which("typos") is None, reason="needs typos")
def test_commit_msg_spelling(checkout: Checkout, capsys: pytest.CaptureFixture[str]) -> None:
    # where git keeps it, out of the staged changes
    message = checkout.root / ".git" / "MSG"
    # an American spelling, put together so that the typos hook doesn't flag this file itself
    american = "optimi" + "ze"
    message.write_text(f"README.md: {american} it\n")
    assert hooks.run_commit_msg(checkout, ".git/MSG") == 1
    assert "Spelling mistakes" in capsys.readouterr().err
    # git's comments and the diff of commit -v aren't checked
    scissors = "# ------------------------ >8 ------------------------"
    message.write_text(f"README.md: tidy it\n# {american}\n{scissors}\n{american}\n")
    assert hooks.run_commit_msg(checkout, ".git/MSG") == 0


def prepared(
    checkout: Checkout, source: str = "", text: str = "\n# Please enter the commit message\n"
) -> str:
    # where git keeps it, out of the staged changes
    message = checkout.root / ".git" / "MSG"
    message.write_text(text)
    assert hooks.run_prepare_commit_msg(checkout, ".git/MSG", source) == 0
    return message.read_text()


def test_prepare_commit_msg(checkout: Checkout) -> None:
    stage_version(checkout, "local/two", "1.0-2")
    assert prepared(checkout).startswith("upgpkg: two 1.0-2\n\n# Please enter")
    git(checkout.root, "reset", "-q", "--hard")
    (checkout.root / "one" / "PKGBUILD").write_text("pkgname=y\n")
    git(checkout.root, "add", "-A")
    assert prepared(checkout).startswith("one: \n")
    (checkout.root / "README.md").write_text("changed\n")
    git(checkout.root, "add", "-A")
    assert prepared(checkout).startswith(
        "# The staged changes are in several scopes, one commit each: README.md one\n"
    )
    # -m, -F and the like, and messages with text, stay as they are
    assert prepared(checkout, "message") == "\n# Please enter the commit message\n"
    assert prepared(checkout, "", "one: mine\n") == "one: mine\n"


def test_install_message_hooks(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert hooks.install_message_hooks(tmp_path) == 0
    script = (tmp_path / "commit-msg").read_text()
    assert "grep -q '^cmd_commit_msg()'" in script
    assert 'exec "$script" commit-msg "$file" "$@"' in script
    assert (tmp_path / "prepare-commit-msg").stat().st_mode & 0o111
    # its own hooks are replaced, others are left alone
    assert hooks.install_message_hooks(tmp_path) == 0
    (tmp_path / "commit-msg").write_text("#!/bin/sh\nmine\n")
    assert hooks.install_message_hooks(tmp_path) == 1
    assert "Not replacing the existing" in capsys.readouterr().err
