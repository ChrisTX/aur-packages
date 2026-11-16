"""The completions of the shells: what the word being typed can become, from the command table.

The scripts of completions/ only pass the command line to aur-packages __complete, which prints a
candidate per line, with a tab and its description where there is one, or :files or :dirs for the
shell to complete paths itself.
"""

from collections.abc import Sequence

from aur_packages.cli import TABLE, Command, Completer, Option
from aur_packages.repo import BUILD_TEMPLATES, Checkout


def find_option(command: Command, word: str) -> Option | None:
    name = word.split("=", 1)[0]
    for option in command.options:
        if name in option.names:
            return option
    return None


def values(checkout: Checkout, completer: Completer) -> list[str]:
    """The candidates of a kind of argument, without descriptions."""
    if isinstance(completer, tuple):
        return list(completer)
    packages = checkout.package_dirs()
    match completer:
        case "packages":
            return packages
        case "aur-packages":
            return [d for d in packages if "/" not in d]
        case "local-packages":
            return [d for d in packages if d.startswith("local/")]
        case "overrides":
            return [d for d in packages if d.startswith("overrides/")]
        case "buildables":
            return [*BUILD_TEMPLATES, *packages]
        case "files":
            return [":files"]
        case "dirs":
            return [":dirs"]
        case "commands":
            return [c.name for c in TABLE.commands.values() if not c.hidden]
    return []


def matching(candidates: Sequence[str], current: str, prefix: str = "") -> list[str]:
    """The candidates that start with the word typed, or the shell's own path completion."""
    if candidates and candidates[0] in (":files", ":dirs"):
        return [candidates[0]]
    return [prefix + c for c in candidates if (prefix + c.split("\t", 1)[0]).startswith(current)]


def complete(checkout: Checkout, words: Sequence[str]) -> list[str]:
    """The candidates for the last of the words, the command line after the program's name.

    bash passes an option's value after = as words of their own (--target, =, aarch64), the other
    shells as one word (--target=aarch64).
    """
    *before, current = words or [""]
    if len(before) >= 2 and before[-1] == "=":
        before, value_of = before[:-2], before[-2]
    else:
        value_of = None
    command: Command | None = None
    sub: Command | None = None
    expect: Option | None = None
    used: set[Option] = set()
    positionals = 0
    ended = False
    for word in before:
        if expect is not None:
            expect = None
            continue
        if ended:
            positionals += 1
            continue
        if word == "--":
            ended = True
            continue
        target = sub or command
        if word.startswith("-") and target is not None:
            option = find_option(target, word)
            if option is not None:
                used.add(option)
                if option.value is not None and "=" not in word:
                    expect = option
            continue
        if command is None:
            command = TABLE.get(word)
            if command is None:
                return []
            continue
        if command.subcommands and sub is None:
            sub = next((s for s in command.subcommands if s.name == word), None)
            if sub is None:
                return []
            continue
        positionals += 1

    if command is None:
        candidates = [f"{c.name}\t{c.summary()}" for c in TABLE.commands.values() if not c.hidden]
        return matching(candidates, current)
    target = sub or command
    if ended and command.passthrough:
        return []
    if value_of is not None:
        option = find_option(target, value_of)
        return matching(values(checkout, option.complete), current) if option and option.value else []
    if expect is not None:
        return matching(values(checkout, expect.complete), current)
    if current.startswith("-") and "=" in current:
        option = find_option(target, current)
        if option is None or option.value is None:
            return []
        name = current.split("=", 1)[0]
        return matching(values(checkout, option.complete), current, f"{name}=")
    if current.startswith("-") and not ended:
        candidates = [
            f"{name}\t{o.help}" for o in target.options if o.repeat or o not in used for name in o.names
        ]
        return matching(candidates, current)
    if command.subcommands and sub is None:
        return matching([f"{s.name}\t{s.summary()}" for s in command.subcommands], current)
    if isinstance(target.arguments, tuple) and positionals:
        return []
    return matching(values(checkout, target.arguments), current)
