"""The command table, the help, the dispatch and the completions."""

from pathlib import Path

import pytest

from aur_packages import cli
from aur_packages.completion import complete
from aur_packages.repo import Checkout


@pytest.fixture
def checkout(tmp_path: Path) -> Checkout:
    for folder in ("alpha", "local/gamma", "overrides/delta"):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / "PKGBUILD").write_text("pkgname=x\n")
    return Checkout(tmp_path, tmp_path)


def run(checkout: Checkout, *argv: str) -> int:
    return cli.run(checkout.root, checkout.cwd, list(argv))


def test_list(checkout: Checkout, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(checkout, "list") == 0
    assert capsys.readouterr().out == "alpha\nlocal/gamma\noverrides/delta\n"
    assert run(checkout, "list", "--local") == 0
    assert capsys.readouterr().out == "local/gamma\n"
    assert run(checkout, "list", "--templates") == 0
    assert capsys.readouterr().out == "powershell-core\npowershell-full\n"


def test_usage_errors(checkout: Checkout, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(checkout, "nope") == 2
    assert "unknown command: nope" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exit_info:
        run(checkout, "list", "--bogus")
    assert exit_info.value.code == 2


def test_help(checkout: Checkout, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(checkout, "help") == 0
    text = capsys.readouterr().out
    assert text.startswith("Usage: aur-packages COMMAND")
    assert "  overrides remove [--force] PACKAGE..." in text
    # paths and options aren't broken at their hyphens
    assert "refs/aur-packages/pushed/PACKAGE" in text
    assert all(len(line) <= cli.WIDTH for line in text.splitlines())
    assert run(checkout, "push", "--help") == 0
    assert capsys.readouterr().out.startswith("Usage: aur-packages push")


def test_every_command_documented() -> None:
    for command in cli.TABLE.commands.values():
        assert command.help, command.name
        for option in command.options:
            assert option.help, (command.name, option.names)


def candidates(checkout: Checkout, *words: str) -> list[str]:
    return [line.split("\t", 1)[0] for line in complete(checkout, list(words))]


def test_complete_commands(checkout: Checkout) -> None:
    assert "push" in candidates(checkout, "")
    assert candidates(checkout, "pu") == ["pull", "push", "publish"]
    assert "pins" in candidates(checkout, "p")
    assert candidates(checkout, "nope", "") == []


def test_complete_options_and_values(checkout: Checkout) -> None:
    assert "--exclude" in candidates(checkout, "push", "--")
    assert candidates(checkout, "push", "--exclude", "") == ["alpha"]
    assert candidates(checkout, "build", "--target", "") == ["aarch64", "aarch64-native", "i686"]
    # zsh, fish and PowerShell pass --opt=value as one word, bash as three
    assert candidates(checkout, "build", "--target=aarch64-") == ["--target=aarch64-native"]
    assert candidates(checkout, "build", "--target", "=", "aarch64-") == ["aarch64-native"]
    assert candidates(checkout, "build", "--repo", "") == [":dirs"]
    # an option given once isn't offered again, one that repeats is
    assert "--force" not in candidates(checkout, "push", "--force", "--")
    assert "--exclude" in candidates(checkout, "push", "--exclude", "alpha", "--")


def test_complete_arguments(checkout: Checkout) -> None:
    assert candidates(checkout, "build", "") == [
        "powershell-core",
        "powershell-full",
        "alpha",
        "local/gamma",
        "overrides/delta",
    ]
    assert candidates(checkout, "publish", "") == ["local/gamma"]
    assert candidates(checkout, "overrides", "") == ["check", "add", "pull", "remove"]
    assert candidates(checkout, "overrides", "pull", "") == ["overrides/delta"]
    assert candidates(checkout, "completion", "") == ["bash", "zsh", "fish", "pwsh"]
    assert candidates(checkout, "completion", "bash", "") == []
    assert candidates(checkout, "sysupgrade", "--", "") == []
    assert candidates(checkout, "commit-msg", "") == [":files"]
