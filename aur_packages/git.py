"""Running git, and the remotes of the AUR and of Arch Linux's packaging."""

import os
import subprocess


def git(*arguments: str, env: dict[str, str] | None = None, stdin: str | None = None) -> str:
    """The output of a git command, which has to succeed."""
    environment = {**os.environ, **env} if env else None
    return subprocess.run(
        ["git", *arguments], input=stdin, capture_output=True, text=True, check=True, env=environment
    ).stdout.strip()


def paths(command: str, *arguments: str) -> list[str]:
    """The paths a git command lists, NUL-separated (-z right after the command, never after a --):
    as they are, without the quoting of unusual characters (core.quotePath) of the line-separated
    output, and unstripped.
    """
    output = subprocess.run(
        ["git", command, "-z", *arguments], capture_output=True, text=True, check=True
    ).stdout
    return [path for path in output.split("\0") if path]


def ok(*arguments: str) -> bool:
    """Whether a git command succeeds, quietly."""
    return subprocess.run(["git", *arguments], capture_output=True, check=False).returncode == 0


def run(*arguments: str) -> int:
    """A git command whose output goes to the terminal, as its exit code."""
    return subprocess.run(["git", *arguments], check=False).returncode


def sign() -> list[str]:
    """-S for the commits made with commit-tree and subtree, if commits are signed (commit.gpgsign)."""
    signing = subprocess.run(
        ["git", "config", "--bool", "commit.gpgsign"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return ["-S"] if signing == "true" else []


def aur_url(pkgbase: str) -> str:
    """The AUR's git repository of a package, read-only over HTTPS ($AUR_PACKAGES_AUR for the tests)."""
    return f"{os.environ.get('AUR_PACKAGES_AUR', 'https://aur.archlinux.org')}/{pkgbase}.git"


def aur_head(pkgbase: str) -> str | None:
    """The AUR's master of a package, empty if the AUR doesn't have it, None if it couldn't be reached."""
    result = subprocess.run(
        ["git", "ls-remote", aur_url(pkgbase), "refs/heads/master"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.split("\t", 1)[0].strip()
