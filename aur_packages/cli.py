"""The commands of aur-packages: one table, from which the help, the parsing and the completions come."""

import argparse
import sys
import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from aur_packages import aur, build, checks, hooks, keys, overrides, pins, tray, updates, upstream
from aur_packages.repo import BUILD_TEMPLATES, Checkout, SelectionError
from aur_packages.tools import MissingTools

# What the arguments or an option's value complete to: a kind, or the choices
#   packages        all packages (folders, as list prints them)
#   aur-packages    the packages at the top level
#   local-packages  the packages of local/
#   overrides       the packages of overrides/
#   buildables      the packages and the build templates
#   files, dirs     paths
Completer = str | tuple[str, ...] | None

Runner = Callable[[Checkout, argparse.Namespace], int]

WIDTH = 100
INDENT = 12


@dataclass(frozen=True)
class Option:
    """An option: its spellings, and the name of its value if it takes one."""

    names: tuple[str, ...]
    help: str
    value: str | None = None
    complete: Completer = None
    repeat: bool = False
    # Spellings still accepted, e.g. by the hooks of the packages, but neither documented nor completed
    aliases: tuple[str, ...] = ()

    def dest(self) -> str:
        """The attribute of the parsed arguments: the first long spelling's name."""
        long = next((name for name in self.names if name.startswith("--")), self.names[0])
        return long.lstrip("-").replace("-", "_")


@dataclass(frozen=True)
class Command:
    """A command or a subcommand, with its synopsis (after the name) and its help."""

    name: str
    synopsis: str
    help: str
    options: tuple[Option, ...] = ()
    arguments: Completer = None
    subcommands: tuple[Command, ...] = ()
    hidden: bool = False
    run: Runner | None = None
    # Arguments after -- belong to another program (sysupgrade's aur sync)
    passthrough: bool = False
    # The subcommand without one given (overrides: check)
    default: str | None = None

    def summary(self) -> str:
        """The first sentence of the help, shortened at a word, for the completions."""
        return textwrap.shorten(self.help.split(". ")[0].rstrip("."), 60, placeholder="…")


@dataclass
class Table:
    """The commands by name, in the order of the help."""

    commands: dict[str, Command] = field(default_factory=dict)

    def add(self, command: Command) -> None:
        self.commands[command.name] = command

    def get(self, name: str) -> Command | None:
        return self.commands.get(name)


def run_list(checkout: Checkout, args: argparse.Namespace) -> int:
    if args.templates:
        names = list(BUILD_TEMPLATES)
    elif args.local:
        names = [d for d in checkout.package_dirs() if d.startswith("local/")]
    else:
        names = checkout.package_dirs()
    for name in names:
        print(name)
    return 0


COMPLETION_FILES = {
    "bash": "aur-packages.bash",
    "zsh": "_aur-packages",
    "fish": "aur-packages.fish",
    "pwsh": "aur-packages.ps1",
}


def run_completion(checkout: Checkout, args: argparse.Namespace) -> int:
    sys.stdout.write((checkout.root / "completions" / COMPLETION_FILES[args.choice]).read_text())
    return 0


def with_arguments(args: argparse.Namespace, least: int, most: int, run: Callable[[list[str]], int]) -> int:
    """Run a command with a number of positional arguments, or fail with a usage error."""
    given: list[str] = args.arguments
    if not least <= len(given) <= most:
        expected = f"{least} argument" if least == most == 1 else f"{least} to {most} arguments"
        print(f"aur-packages: expected {expected}, got {len(given)}", file=sys.stderr)
        return 2
    return run(given)


def signing(args: argparse.Namespace) -> bool | None:
    """--sign or --no-sign, the later one winning; None without either."""
    if args.sign and args.no_sign:
        print("aur-packages: --sign and --no-sign contradict each other", file=sys.stderr)
        raise SystemExit(2)
    return True if args.sign else False if args.no_sign else None


def system_repo(args: argparse.Namespace) -> bool | None:
    """--system-repo or --no-system-repo; None without either, for the default."""
    if args.system_repo and args.no_system_repo:
        print("aur-packages: --system-repo and --no-system-repo contradict each other", file=sys.stderr)
        raise SystemExit(2)
    return True if args.system_repo else False if args.no_system_repo else None


def run_build(checkout: Checkout, args: argparse.Namespace) -> int:
    if args.chroot and args.local:
        print("aur-packages: --chroot and --local contradict each other", file=sys.stderr)
        return 2
    settings = build.Build(
        method="local" if args.local else "chroot",
        install=args.install,
        dry_run=args.dry_run,
        keep=args.keep,
        add=args.add,
        signing=signing(args),
        dotnet_bin=args.dotnet_bin,
        nuget_bin=args.nuget_bin,
        testing=args.testing,
        sanitise=args.sanitize or "",
        target=args.target or "",
        reuse=args.repo or "",
        fetch_keys=args.auto_key_retrieve,
        system_repo=system_repo(args),
    )
    return build.run_build(checkout, args.arguments, settings)


SECTIONS = ("PowerShell", ".NET", "SourceMod", "Other")
SANITISERS = ("undefined", "address", "address,undefined")
TARGETS = tuple(build.TARGETS)

DRY_RUN = Option(("-n", "--dry-run"), "only show what would be done")

TABLE = Table()
for _command in (
    Command(
        "pull",
        "",
        "Pull the packages from the AUR (aurpublish --pull)",
        options=(DRY_RUN,),
        arguments="aur-packages",
        run=lambda checkout, args: aur.run_pull(checkout, args.arguments, args.dry_run),
    ),
    Command(
        "push",
        "",
        "Check, then push the packages to the AUR (aurpublish), or with --no-check without the checks, "
        "e.g. while a linter isn't installed. Leaves out packages without commits since their last "
        "push (refs/aur-packages/pushed/PACKAGE), which --force pushes anyway. --exclude PACKAGE "
        "leaves a package out (repeatable), e.g. one whose AUR request is still pending. A pushed "
        "package leaves the tray's list of outdated packages once its version is at least the new "
        "one",
        options=(
            Option(("--no-check",), "push without running the checks", aliases=("--nocheck",)),
            Option(("--force",), "also push packages without commits since their last push"),
            Option(("--exclude",), "leave a package out", "PACKAGE", "aur-packages", repeat=True),
            DRY_RUN,
        ),
        arguments="aur-packages",
        run=lambda checkout, args: aur.run_push(
            checkout, args.arguments, args.exclude or [], args.no_check, args.force, args.dry_run
        ),
    ),
    Command(
        "adopt",
        "PACKAGE...",
        "Merge the history the AUR has of packages into their subtrees, keeping their files, so that "
        "push can push on top of it: for a package that was on the AUR before, deleted or taken over "
        "from another maintainer (the AUR only accepts pushes on top of its history)",
        options=(DRY_RUN,),
        arguments="aur-packages",
        run=lambda checkout, args: aur.run_adopt(checkout, args.arguments, args.dry_run),
    ),
    Command(
        "publish",
        "[--section SECTION] PACKAGE...",
        "Move packages of local/ to the top level, to push them to the AUR: with the history push "
        "pushes, the package's earlier history at the top level (if it was there before, the AUR's "
        "included) followed by its commits in local/, and its row of README.md in the table of "
        "SECTION (default: Other). Commits the move (with the checks of the hooks) and the history; "
        "doesn't push. Refuses a package the AUR has another history of, unless --adopt merges it, "
        "as adopt does, once the package is ours on the AUR",
        options=(
            Option(("--section",), "the table of README.md", "SECTION", SECTIONS),
            Option(("--adopt",), "merge the AUR's history of a package that's ours there now"),
            DRY_RUN,
        ),
        arguments="local-packages",
        run=lambda checkout, args: aur.run_publish(
            checkout, args.arguments, args.section or "Other", args.adopt, args.dry_run
        ),
    ),
    Command(
        "updates",
        "",
        "Show which packages have a newer upstream version with the .nvchecker.toml of each (pkgctl "
        "version check), without changing anything. --state writes the result to "
        "~/.local/state/aur-packages/updates.json for the tray icon instead (see tray), keeping the "
        "entries of packages that weren't checked or whose check failed; --state --retry also checks "
        "the packages that hit GitHub's rate limit again once it resets (systemd-run)",
        options=(
            Option(("--state",), "write the result for the tray icon"),
            Option(("--retry",), "check rate-limited packages again once the limit resets"),
        ),
        arguments="packages",
        run=lambda checkout, args: updates.run_updates(checkout, args.arguments, args.state, args.retry),
    ),
    Command(
        "upgrade",
        "",
        "Upgrade the packages to their latest upstream version with the .nvchecker.toml of each "
        "(pkgctl version upgrade), move their pins to it (see pins --update), then format the "
        "PKGBUILDs and regenerate .SRCINFO; then show the upstream references of the upgraded "
        "packages against their new versions (see upstream), e.g. backports they contain now. Fails "
        "if a pin couldn't be moved",
        arguments="packages",
        run=lambda checkout, args: pins.run_upgrade(checkout, args.arguments),
    ),
    Command(
        "check",
        "",
        "Run the checks of .pre-commit-config.yaml with prek or pre-commit, or with --manual also the "
        "ones that only run on request (termux-language-server). Packages given, only theirs: the "
        "hooks of their own .pre-commit-config.yaml, and those of the top level that check single "
        "packages (templates, gitignore, keys, quoting, pins, pkgrel, upstream, maintainers; for overrides/ only templates, gitignore and keys)",
        options=(Option(("--manual",), "also run the checks that only run on request"),),
        arguments="packages",
        run=lambda checkout, args: checks.run_check(checkout, args.arguments, args.manual),
    ),
    Command(
        "keys",
        "[--fetch] [PACKAGE...]",
        "Check that each package ships the PGP keys of its validpgpkeys, as "
        "keys/pgp/<fingerprint>.asc like Arch Linux's packaging, and only those (run by the keys "
        "hook): so that its sources can be verified without a keyserver. --fetch adds the missing "
        "ones from a keyserver, through a temporary keyring. build and sysupgrade import the shipped "
        "keys before building, and stop with the missing ones (-K fetches them)",
        options=(Option(("--fetch",), "add the missing keys from a keyserver"),),
        arguments="packages",
        run=lambda checkout, args: keys.run_keys(checkout, args.arguments, args.fetch),
    ),
    Command(
        "upstream",
        "[--check] [PACKAGE...]",
        "Show the upstream issues, pull requests and commits on GitHub the comments of the PKGBUILDs "
        "refer to (https://github.com/…/pull/1, owner/repo#1, #1 of the package's own repository, "
        "owner/repo@commit) with their state, and for a merged pull request or a commit whether the "
        "upstream version the package builds contains it (its source of that repository at its tag or "
        "commit, or a git submodule of its own), else which release does; with the verb of their "
        "'# upstream:' directive, and what the directives want done: a backport that can go, say. "
        "--check checks the directives, offline (run by the upstream hook): every patch a PKGBUILD "
        "applies has one in the comment right above it",
        options=(Option(("--check",), "check the directives of the patches, offline"),),
        arguments="packages",
        run=lambda checkout, args: upstream.run_upstream(checkout, args.arguments, args.check),
    ),
    Command(
        "commits",
        "",
        "pins --online, its earlier name",
        options=(Option(("--update",), "rewrite the stale pins"),),
        arguments="packages",
        hidden=True,
        run=lambda checkout, args: pins.run_online(checkout, args.arguments, args.update),
    ),
    Command(
        "build",
        "",
        "Build packages or a template (powershell-core, powershell-full) and their dependencies in "
        "order, in a clean chroot into a private throwaway repo (default), or --local (makepkg -fCd, "
        "--install to install each result). --dry-run prints the plan, --keep keeps the chroot repo. "
        "In a chroot, --dotnet-bin builds with Microsoft's .NET (dotnet-build-deps-10.0-bin, "
        "the SDK of the current .NET built by aur sync) and --nuget-bin with the libraries from nuget.org "
        "(powershell-build-deps-bin) instead of the source-built ones. A .NET Arch Linux doesn't "
        "have (dotnet-build-deps-11.0-bin) is always Microsoft's. --target aarch64 also cross-builds "
        "the architecture-specific packages for aarch64 against an Arch Linux ARM root, if their "
        "PKGBUILDs build for it ($CARCH, $ROOTFS_DIR), --target "
        "aarch64-native builds everything in that root under QEMU (qemu-user-static-binfmt), with "
        "Microsoft's .NET, and --target i686 the packages for i686 in an Arch Linux 32 root, natively, "
        "without .NET. --repo DIR continues in the repo of an earlier --keep, skipping the "
        "packages already built there. Packages that depend on lib32-* packages build in a multilib "
        "chroot (multilib-devel). --sanitize undefined|address|address,undefined makes test builds "
        "with the sanitisers (their -fsanitize flags in the chroots' makepkg.conf) and keeps their "
        "repo; check() runs on them too. --testing builds against Arch Linux's testing repositories "
        "(devtools' extra-testing and multilib-testing), in chroots of their own, for a system that "
        "uses them. The chroots are in /var/lib/aur-packages-chroot ($AUR_BUILD_CHROOT), next to "
        "the Arch Linux ARM root (aarch64) and the Arch Linux 32 root (i686), not in aurutils' /var/lib/aurbuild. --add adds the "
        "packages, their -debug packages and the AUR dependencies built to the system's aurutils "
        "repository (aur repo) once all have been built, and against the testing repositories if "
        "the system uses them; run it as the repository's owner, e.g. the aurutils user. They're "
        "signed ($GPGKEY, else gpg's default key, as aur build) if the database is or makepkg signs "
        "(sign in BUILDENV), or as --sign or --no-sign say",
        options=(
            Option(("--chroot",), "build in a clean chroot (default)"),
            Option(("--local",), "build with makepkg -fCd"),
            Option(("--install",), "install each result of a local build"),
            Option(("-n", "--dry-run"), "print the plan"),
            Option(("--keep",), "keep the chroot repo"),
            Option(("--add",), "add the packages to the system's aurutils repository"),
            Option(("--sign",), "sign the packages --add adds"),
            Option(("--no-sign",), "don't sign the packages --add adds"),
            Option(("--dotnet-bin",), "build with Microsoft's .NET"),
            Option(
                ("--nuget-bin",),
                "build with the libraries from nuget.org (powershell-build-deps-bin)",
                aliases=("--libs-bin",),
            ),
            Option(("--testing",), "build against Arch Linux's testing repositories"),
            Option(("--sanitize",), "make test builds with the sanitisers", "SANITISERS", SANITISERS),
            Option(("--target",), "build for another architecture", "TARGET", TARGETS),
            Option(("--repo",), "continue in the repo of an earlier --keep", "DIR", "dirs"),
            Option(("-K", "--auto-key-retrieve"), "fetch the PGP keys the packages need, like aur sync -K"),
            Option(("--system-repo",), "take dependencies from the system's aurutils repository"),
            Option(("--no-system-repo",), "build every dependency from this repository"),
        ),
        arguments="buildables",
        run=lambda checkout, args: run_build(checkout, args),
    ),
    Command(
        "sysupgrade",
        "[--sign|--no-sign] [-- AUR_SYNC_OPTION...]",
        "aur sync -u with our packages first: the packages of the top level, local/ and overrides/ in "
        "the aurutils repository with a newer version here, and those of overrides/ and local/ newer "
        "than the installed package they replace (Arch Linux's, the AUR's), are built and added (build --add), then "
        "aur sync -u updates the rest, leaving all of ours out; both sign as build --add does",
        options=(
            Option(("-S", "--sign"), "sign the packages added"),
            Option(("--no-sign",), "don't sign the packages added"),
            Option(("-K", "--auto-key-retrieve"), "fetch the PGP keys the packages need, like aur sync -K"),
            Option(("--system-repo",), "take dependencies from the system's aurutils repository"),
            Option(("--no-system-repo",), "build every dependency from this repository"),
            Option(("--repo",), "continue in the repo of a failed sysupgrade", "DIR", "dirs"),
        ),
        passthrough=True,
        run=lambda checkout, args: build.run_sysupgrade(
            checkout,
            signing(args),
            args.passthrough,
            build.Build(
                fetch_keys=args.auto_key_retrieve, reuse=args.repo or "", system_repo=system_repo(args)
            ),
        ),
    ),
    Command(
        "sync",
        "",
        "Copy templates/package into the packages and write the configuration at the top level, or "
        "with --dry-run only report the files that differ, and fail then",
        options=(Option(("-n", "--dry-run"), "only report the files that differ", aliases=("--check",)),),
        arguments="packages",
        run=lambda checkout, args: checks.run_sync(checkout, args.arguments, args.dry_run),
    ),
    Command(
        "setup",
        "",
        "Install the git hooks that run the checks before each commit, replacing aurpublish's, fill "
        "in the summary of the commit message and check it",
        run=lambda checkout, args: hooks.run_setup(checkout),
    ),
    Command(
        "tray",
        "install|remove",
        "Install a daily update check of this checkout's packages (the systemd user units of "
        "systemd/, updates --state) and a tray icon (tray run, autostarted) that shows the outdated "
        "packages and announces new versions once; or remove them again",
        subcommands=(
            Command(
                "install",
                "",
                "Install the update check and the tray icon",
                run=lambda c, a: tray.run_install(c),
            ),
            Command("remove", "", "Remove them", run=lambda c, a: tray.run_remove(c)),
            Command(
                "run", "", "Show the tray icon (needs python-gobject)", run=lambda c, a: tray.run_icon(c)
            ),
        ),
    ),
    Command(
        "commit-msg",
        "FILE",
        "Check a commit message against the convention in CONTRIBUTING.md (run by the commit-msg hook)",
        arguments="files",
        run=lambda checkout, args: with_arguments(args, 1, 1, lambda f: hooks.run_commit_msg(checkout, f[0])),
    ),
    Command(
        "prepare-commit-msg",
        "FILE [SOURCE]",
        "Fill in the summary of an empty commit message from the staged changes: upgpkg: with the "
        "staged version when they change a package's version, else the scope (run by the "
        "prepare-commit-msg hook)",
        arguments="files",
        run=lambda checkout, args: with_arguments(
            args, 1, 3, lambda f: hooks.run_prepare_commit_msg(checkout, f[0], f[1] if len(f) > 1 else "")
        ),
    ),
    Command(
        "gitignore",
        "",
        "Check that each package's .gitignore has the patterns of toptal's archlinuxpackages template, "
        "as CONTRIBUTING.md asks, next to its own (run by the gitignore hook)",
        arguments="packages",
        run=lambda checkout, args: checks.run_gitignore(checkout, args.arguments),
    ),
    Command(
        "pkgrel",
        "",
        "Check that the packages published to the AUR (the top level) have a whole pkgrel: the .1 of "
        "local/ and overrides/, above what they replace, has no reason there (run by the pkgrel hook)",
        arguments="packages",
        run=lambda checkout, args: checks.run_pkgrel(checkout, args.arguments),
    ),
    Command(
        "quoting",
        "",
        "Check the quoting of the metadata arrays (depends, optdepends, …) of the PKGBUILDs against "
        "the convention in CONTRIBUTING.md (run by the quoting hook)",
        arguments="packages",
        run=lambda checkout, args: checks.run_quoting(checkout, args.arguments),
    ),
    Command(
        "pins",
        "[--online|--update]",
        "Check that the _commit of a version like git describe's (…r83.g4b8b3d3) is the commit it "
        "names, without the network (run by the pins hook). --online shows, for each package that pins "
        "something, whether its pins are the ones its version names: the upstream commit its pkgver "
        "was published from (the commit a git describe pkgver names, or the NuGet package's repository "
        "commit), or what pins.toml says (the VMR's commits, branch heads, values in files of a "
        "release), flagging stale ones; --update rewrites them and refreshes the checksums and .SRCINFO",
        options=(
            Option(("--online",), "look up what every pin should be"),
            Option(("--update",), "rewrite the stale pins (online)"),
        ),
        arguments="packages",
        run=lambda checkout, args: (
            pins.run_online(checkout, args.arguments, args.update)
            if args.online or args.update
            else pins.run_pins(checkout, args.arguments)
        ),
    ),
    Command(
        "readme",
        "",
        "Check README.md's tables of the packages against the packages: a row for each, with its "
        "link, packages and pkgdesc (run by the readme hook)",
        run=lambda checkout, args: checks.run_readme(checkout),
    ),
    Command(
        "maintainers",
        "[--aur]",
        "Check the # Maintainer: and # Contributor: lines of the PKGBUILDs: "
        "the Maintainer lines first, addresses obscured as name at domain dot tld, ours among them "
        "(run by the maintainers hook); --aur compares the Maintainer lines with the maintainers and "
        "co-maintainers on the AUR (maintainers.toml maps their usernames to names), and says when a "
        "package of local/ has been handed to us there. updates --state does that too, for the "
        "tray. The commit-msg hook checks that the staged PKGBUILDs list the commit's author",
        options=(
            Option(("--aur",), "compare with the maintainers on the AUR"),
            Option(("--json",), "print the comparison with the AUR as JSON, with --aur"),
        ),
        arguments="packages",
        run=lambda checkout, args: checks.run_maintainers(checkout, args.arguments, args.aur, args.json),
    ),
    Command(
        "overrides",
        "",
        "Compare, add, pull or remove the packages of overrides/",
        subcommands=(
            Command(
                "check",
                "[PACKAGE...]",
                "Compare the packages of overrides/ with Arch Linux's repositories, and fail if Arch "
                "has caught up with one, which then isn't needed any more. Compares with the version "
                "pacman would install, from the repositories in pacman.conf's order, the testing ones "
                "included",
                arguments="overrides",
                run=lambda checkout, args: overrides.run_check(checkout, args.arguments),
            ),
            Command(
                "add",
                "PACKAGE",
                "Import Arch Linux's packaging of a package as overrides/<pkgbase>, a subtree of it, "
                "and prepare the first commit of the changes: the README.md row, the .gitignore and a "
                "pkgrel below Arch's next release",
                options=(DRY_RUN,),
                arguments="arch-package",
                run=lambda checkout, args: with_arguments(
                    args, 1, 1, lambda given: overrides.run_add(checkout, given[0], args.dry_run)
                ),
            ),
            Command(
                "pull",
                "PACKAGE...",
                "Merge Arch Linux's updates of the overrides' packaging into them",
                options=(DRY_RUN,),
                arguments="overrides",
                run=lambda checkout, args: overrides.run_pull(checkout, args.arguments, args.dry_run),
            ),
            Command(
                "remove",
                "[--force] PACKAGE...",
                "Remove overrides once Arch Linux has caught up with them (or with --force anyway), "
                "with their README.md rows, and commit",
                options=(Option(("--force",), "remove it even if Arch Linux hasn't caught up"), DRY_RUN),
                arguments="overrides",
                run=lambda checkout, args: overrides.run_remove(
                    checkout, args.arguments, args.force, args.dry_run
                ),
            ),
        ),
        default="check",
    ),
    Command(
        "list",
        "",
        "List the packages, with --local only those of local/, or with --templates the build templates",
        options=(
            Option(("--local",), "only the packages of local/"),
            Option(("--templates",), "the build templates instead"),
        ),
        run=run_list,
    ),
    Command(
        "completion",
        "bash|zsh|fish|pwsh",
        "Print the completion script for a shell, see CONTRIBUTING.md",
        arguments=tuple(COMPLETION_FILES),
        run=run_completion,
    ),
    Command("help", "[COMMAND]", "Show this help, or a command's", arguments="commands"),
):
    TABLE.add(_command)

INTRO = """\
Usage: aur-packages COMMAND [PACKAGE...]

Commands work on all packages unless packages are given, by folder or name. The packages at the top \
level are the AUR's; local/ holds packages of ours that aren't on the AUR, overrides/ Arch Linux's \
packages with changes of ours (subtrees of Arch's packaging, in Arch's style). Both are built, checked \
and tracked here, but never published to the AUR: pull, push and adopt refuse them, and publish moves \
a package of local/ to the top level.

Run from a checkout (./aur-packages), it works on that one. From elsewhere, e.g. a symlink or a copy \
on PATH, it works on the checkout of the current directory, else the one $AUR_PACKAGES_HOME names, \
else the one the symlink points into. aur-packages COMMAND --help shows a command's help.
"""


def wrap(text: str, initial: str = "", subsequent: str = "") -> str:
    """Text wrapped to the width of the help, never breaking paths or options at their hyphens."""
    return textwrap.fill(
        text,
        WIDTH,
        initial_indent=initial,
        subsequent_indent=subsequent,
        break_on_hyphens=False,
        break_long_words=False,
    )


def entry(name: str, command: Command) -> str:
    """A command's entry in the help: name and synopsis, then its help, indented."""
    if command.synopsis or len(name) > INDENT - 3:
        head = f"  {name} {command.synopsis}".rstrip() + "\n"
        initial = " " * INDENT
    else:
        head = ""
        initial = f"  {name:<{INDENT - 2}}"
    return head + wrap(command.help, initial, " " * INDENT)


def help_text() -> str:
    lines = [wrap(p) if p and not p.startswith("Usage:") else p for p in INTRO.split("\n")]
    entries = []
    for command in TABLE.commands.values():
        if command.hidden:
            continue
        if command.subcommands and command.name == "overrides":
            entries += [entry(f"overrides {sub.name}", sub) for sub in command.subcommands]
        else:
            entries.append(entry(command.name, command))
    return "\n".join(lines) + "\n" + "\n".join(entries) + "\n"


def command_help(command: Command, prog: str = "") -> str:
    text = f"Usage: aur-packages {prog or command.name} {command.synopsis}".rstrip() + "\n\n"
    text += wrap(command.help) + "\n"
    for sub in command.subcommands:
        text += "\n" + entry(sub.name, sub) + "\n"
    if command.options:
        text += "\nOptions:\n"
        for option in command.options:
            spelling = ", ".join(option.names) + (f" {option.value}" if option.value else "")
            text += f"  {spelling:<22} {option.help}\n"
    return text


def wants_help(args: Sequence[str]) -> bool:
    """--help or -h among the options, before a -- that ends them."""
    for arg in args:
        if arg == "--":
            return False
        if arg in ("-h", "--help"):
            return True
    return False


def parser_for(command: Command, prog: str = "") -> argparse.ArgumentParser:
    """The argparse parser of a ported command, from its entry in the table."""
    parser = argparse.ArgumentParser(prog=f"aur-packages {prog or command.name}", add_help=False)
    for option in command.options:
        dest = option.dest()
        names = (*option.names, *option.aliases)
        if option.value is None:
            parser.add_argument(*names, dest=dest, action="store_true")
        else:
            choices = option.complete if isinstance(option.complete, tuple) else None
            action = "append" if option.repeat else "store"
            parser.add_argument(*names, dest=dest, metavar=option.value, choices=choices, action=action)
    if isinstance(command.arguments, tuple):
        parser.add_argument("choice", choices=command.arguments)
    elif command.arguments is not None:
        metavar = {"files": "FILE", "dirs": "DIR", "commands": "COMMAND"}.get(command.arguments, "PACKAGE")
        parser.add_argument("arguments", nargs="*", metavar=metavar)
    return parser


def run(root: Path, cwd: Path, argv: Sequence[str]) -> int:
    """Run the command of argv, the arguments after the program's name."""
    checkout = Checkout(root, cwd)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(help_text())
        return 0
    name, args = argv[0], list(argv[1:])
    if name == "__complete":
        from aur_packages.completion import complete

        for line in complete(checkout, args):
            print(line)
        return 0
    if name == "help":
        target = TABLE.get(args[0]) if args else None
        if args and target is None:
            print(f"aur-packages help: unknown command: {args[0]}", file=sys.stderr)
            return 2
        sys.stdout.write(command_help(target) if target else help_text())
        return 0
    command = TABLE.get(name)
    if command is None:
        print(f"aur-packages: unknown command: {name} (aur-packages help lists them)", file=sys.stderr)
        return 2
    target, prog = command, command.name
    if wants_help(args) and not (command.subcommands and args[0] in {s.name for s in command.subcommands}):
        sys.stdout.write(command_help(command))
        return 0
    if command.subcommands and any(sub.run for sub in command.subcommands):
        subs = {sub.name: sub for sub in command.subcommands}
        if args and args[0] in subs:
            target = subs[args.pop(0)]
        elif command.default:
            target = subs[command.default]
        else:
            print(f"aur-packages {name}: expected one of {', '.join(subs)}", file=sys.stderr)
            return 2
        prog = f"{name} {target.name}"
        if wants_help(args):
            sys.stdout.write(command_help(target, prog))
            return 0
    # Only help and the commands with subcommands have none, and they're handled above
    assert target.run is not None, f"{prog} has nothing to run"
    # The arguments after -- go to another program as they are
    rest: list[str] = []
    if target.passthrough and "--" in args:
        rest = args[args.index("--") + 1 :]
        args = args[: args.index("--")]
    try:
        parsed = parser_for(target, prog).parse_intermixed_args(args)
        parsed.passthrough = rest
        return target.run(checkout, parsed)
    except (SelectionError, MissingTools) as error:
        print(error, file=sys.stderr)
        return 1
