"""External tools: whether they're installed, and the runner of the git hooks."""

import shutil
import sys
from collections.abc import Iterable


class MissingTools(Exception):
    """Tools a command needs that aren't installed."""


def require(what: str, tools: Iterable[tuple[str, str]]) -> None:
    """Fail, naming the packages to install, unless the commands given are installed.

    The tools are (command, package) pairs; what says which command needs them.
    """
    missing: list[str] = []
    for command, package in dict.fromkeys(tools):
        if shutil.which(command) is None:
            missing.append(f"{command} ({package})")
    if missing:
        raise MissingTools(f"{what}: these commands aren't installed: {', '.join(missing)}")


def hook_runner() -> str:
    """prek, the faster reimplementation of pre-commit, where it's installed, else pre-commit."""
    return "prek" if shutil.which("prek") else "pre-commit"


def hook_runner_tool() -> tuple[str, str]:
    """The hook runner for require: prek, unless pre-commit is installed (and prek isn't)."""
    runner = hook_runner()
    return (runner, runner) if shutil.which(runner) else ("prek", "prek")


def warn(message: str) -> None:
    """A message on stderr, prefixed like the errors of the commands."""
    print(f"aur-packages: {message}", file=sys.stderr)
