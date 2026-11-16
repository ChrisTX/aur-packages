"""The git hooks: installing them (setup), and the commit message's (commit-msg, prepare-commit-msg)."""

import re
import subprocess
import sys
from pathlib import Path

from aur_packages import maintainers
from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import hook_runner, hook_runner_tool, require


def git(*arguments: str) -> str:
    return subprocess.run(["git", *arguments], capture_output=True, text=True, check=True).stdout


def git_ok(*arguments: str) -> bool:
    return subprocess.run(["git", *arguments], capture_output=True, check=False).returncode == 0


def staged_version(srcinfo: str) -> str | None:
    """The version of a .SRCINFO in git, given as git show takes it (":dir/.SRCINFO", HEAD:…)."""
    try:
        return Srcinfo.parse(git("show", srcinfo)).version()
    except subprocess.CalledProcessError:
        return None


def summary_line(text: str) -> str:
    """The first line that isn't empty or a comment, which git keeps as the summary."""
    return next((line for line in text.splitlines() if line.strip() and not line.startswith("#")), "")


# Summaries written by git, git subtree (aurpublish) or the AUR
EXEMPT = re.compile(
    r"^(Merge |Revert \"|fixup! |squash! |amend! |Initial upload|Add '.*/' from commit '|Squashed ')"
)
UPGPKG = re.compile(r"^upgpkg: ([^ ]+) ([^ ]+)$")
SCOPE = re.compile(r"^([^ :]+): [^ ]")
# git commit -v puts the diff below this line
SCISSORS = re.compile(r"^# -* >8 -*$")


def scope_exists(checkout: Checkout, scope: str) -> bool:
    """A package (by folder or name) or top-level file or folder; removed ones exist only in HEAD."""
    if (checkout.root / scope).exists() or checkout.package_dir(scope) is not None:
        return True
    return any(
        git_ok("cat-file", "-e", f"HEAD:{path}") for path in (scope, f"local/{scope}", f"overrides/{scope}")
    )


def check_summary(checkout: Checkout, summary: str) -> str | None:
    """What's wrong with the summary of a commit message, if anything."""
    if match := UPGPKG.match(summary):
        scope, version = match.groups()
        folder = checkout.package_dir(scope) or scope
        expected = staged_version(f":{folder}/.SRCINFO")
        if expected is None:
            return f"Not a package with a staged .SRCINFO: {scope}"
        if version != expected:
            return f"The version in the summary is {version}, but {folder}/.SRCINFO has {expected}"
        return None
    if match := SCOPE.match(summary):
        if not scope_exists(checkout, match[1]):
            return f"The scope '{match[1]}' is neither a package nor a top-level file or folder"
        if summary.endswith("."):
            return f"The summary ends with a period: {summary}"
        return None
    return (
        "The summary has to be 'upgpkg: <pkg> <ver>-<rel>' or '<scope>: <summary>', see "
        f"CONTRIBUTING.md: {summary}"
    )


def run_commit_msg(checkout: Checkout, file: str) -> int:
    """Check a commit message: its spelling, its summary, and that its author is credited."""
    require("commit-msg", [("typos", "typos")])
    text = (checkout.cwd / file).read_text()
    summary = summary_line(text)
    if EXEMPT.match(summary):
        return 0
    # The spelling, in British English (.typos.toml), without git's comments and the diff of -v
    lines = []
    for line in text.splitlines():
        if SCISSORS.match(line):
            break
        if not line.startswith("#"):
            lines.append(line)
    if subprocess.run(["typos", "-"], input="\n".join(lines) + "\n", text=True, check=False).returncode:
        print("Spelling mistakes in the commit message, see .typos.toml for names", file=sys.stderr)
        return 1
    if problem := check_summary(checkout, summary):
        print(problem, file=sys.stderr)
        return 1
    # Whoever changes a package is one of its # Maintainer:/# Contributor: lines; not the packages of
    # overrides/, which keep Arch Linux's style
    staged = git("diff", "--cached", "--name-only", "--no-renames", "--diff-filter=d").splitlines()
    packages = [m[1] for path in staged if (m := re.fullmatch(r"((local/)?[^/]+)/PKGBUILD", path))]
    return maintainers.check(packages, author=True) if packages else 0


def run_prepare_commit_msg(checkout: Checkout, file: str, source: str) -> int:
    """Fill in the summary of an empty commit message from the staged changes.

    In one package with a changed version (the staged .SRCINFO against HEAD's), upgpkg: <pkg>
    <ver>-<rel>; in one scope otherwise, "<scope>: "; in several, a comment, as each package is a
    commit of its own. Not for -m and -F, git's own messages, those of a commit, or any with text.
    """
    if source in ("message", "merge", "squash", "commit"):
        return 0
    path = checkout.cwd / file
    text = path.read_text()
    if summary_line(text):
        return 0
    staged = git("diff", "--cached", "--name-only", "--no-renames").splitlines()
    # The top-level file or folder, for local/ and overrides/ the package's name
    scopes = sorted({re.sub(r"^(local|overrides)/([^/]+)/.*", r"\2", p).split("/")[0] for p in staged})
    if len(scopes) > 1:
        summary = f"# The staged changes are in several scopes, one commit each: {' '.join(scopes)}"
    elif scopes:
        scope = scopes[0]
        summary = f"{scope}: "
        folder = checkout.package_dir(scope)
        version = staged_version(f":{folder}/.SRCINFO") if folder else None
        if version and version != staged_version(f"HEAD:{folder}/.SRCINFO"):
            summary = f"upgpkg: {scope} {version}"
    else:
        return 0
    path.write_text(f"{summary}\n{text.rstrip(chr(10))}\n")
    return 0


# The commands the hooks of .pre-commit-config.yaml run (not those of check --manual), with the
# packages that have them, those of CONTRIBUTING.md's pacman line; mago, and pwsh (powershell) for
# PSScriptAnalyzer, are in the AUR
HOOK_TOOLS = (
    ("makepkg", "pacman"),
    ("shfmt", "shfmt"),
    ("shellcheck", "shellcheck"),
    ("shellharden", "shellharden"),
    ("ruff", "ruff"),
    ("biome", "biome"),
    ("tombi", "tombi"),
    ("rumdl", "rumdl"),
    ("typos", "typos"),
    ("systemd-lsp", "systemd-lsp"),
    ("editorconfig-checker", "editorconfig-checker"),
    ("reuse", "reuse"),
    ("mypy", "mypy"),
    ("pytest", "python-pytest"),
    ("mago", "mago"),
    ("pwsh", "powershell"),
)

# The message hooks setup installs: plain scripts instead of the configuration's hooks, which would
# run every check again in these stages. They run the checkout's own ./aur-packages, if it has the
# command (it names cmd_commit_msg() and cmd_prepare_commit_msg() for that), so checkouts of branches
# from before it (or of ./aur, before the rename) are skipped.
MESSAGE_HOOK = """\
#!/bin/sh
# Installed by ./aur-packages setup: see ./aur-packages {command}
top=$(git rev-parse --show-toplevel)
for script in "$top/aur-packages" "$top/aur"; do
  if grep -q '^{function}()' "$script" 2>/dev/null; then
    file=$(realpath "$1")
    shift
    exec "$script" {command} "$file" "$@"
  fi
done
"""
INSTALLED = re.compile(r"^# Installed by \./aur(-packages)? setup", re.MULTILINE)


def install_message_hooks(hooks: Path) -> int:
    """Write the commit-msg and prepare-commit-msg hooks, unless others are there."""
    for command in ("commit-msg", "prepare-commit-msg"):
        path = hooks / command
        if path.exists() and not INSTALLED.search(path.read_text(errors="replace")):
            print(f"Not replacing the existing {path}", file=sys.stderr)
            return 1
        path.write_text(MESSAGE_HOOK.format(command=command, function="cmd_" + command.replace("-", "_")))
        path.chmod(0o755)
        print(f"Installed {path}")
    return 0


def remove_aurpublish_hooks(hooks: Path) -> None:
    """aurpublish's hooks regenerate .SRCINFO, downloading the sources, and rewrite the message."""
    for name in ("pre-commit", "prepare-commit-msg", "post-commit"):
        path = hooks / name
        if path.is_symlink() and str(path.readlink()).startswith("/usr/share/aurpublish/"):
            path.unlink()
            print(f"Removed aurpublish's {name} hook")


def run_setup(checkout: Checkout) -> int:
    """Install the git hooks, after checking that their tools are there, so none is half installed."""
    require("setup (the hooks)", [hook_runner_tool(), *HOOK_TOOLS])
    runner = hook_runner()
    analyzer = "if (-not (Get-Module -ListAvailable PSScriptAnalyzer)) { exit 1 }"
    if subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", analyzer], check=False
    ).returncode:
        print(
            "setup (the hooks): PSScriptAnalyzer isn't installed (powershell-editor-services)",
            file=sys.stderr,
        )
        return 1
    hooks = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip()) / "hooks"
    remove_aurpublish_hooks(hooks)
    # Checkouts of branches from before the configuration are skipped
    subprocess.run([runner, "install", "--allow-missing-config"], check=True)
    return install_message_hooks(hooks)
