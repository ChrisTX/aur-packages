"""Publishing to the AUR: pull, push, adopt, and publish (moving a package of local/ to the top level)."""

import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from aur_packages import checks, maintainers, state
from aur_packages.git import aur_head, aur_url, git, ok, sign
from aur_packages.git import run as run_git
from aur_packages.repo import Checkout, SelectionError
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import hook_runner_tool, require


def run_pull(checkout: Checkout, packages: Sequence[str], dry_run: bool) -> int:
    """Pull the packages from the AUR (aurpublish --pull)."""
    require("pull", [("aurpublish", "aurpublish")])
    for package in checkout.select(packages, aur_only=True):
        if dry_run:
            print(f"Would pull {package}")
        elif subprocess.run(["aurpublish", "--pull", package], check=False).returncode:
            return 1
    return 0


def pushed_ref(package: str) -> str:
    """The ref that records the commit whose subtree of the package push pushed last."""
    return f"refs/aur-packages/pushed/{package}"


def push_needed(package: str) -> bool:
    """Whether HEAD's subtree of the package, what aurpublish pushes, can differ from the last pushed.

    No push recorded, a rewritten history, commits since that change the package, or a merge that
    joins a history to it (adopt's, publish's, git subtree's), which leaves its files as they are.
    Not --full-history: it would count every merge of a history without the package, like the
    subtree pulls of overrides/, for all packages.
    """
    try:
        pushed = git("rev-parse", "-q", "--verify", f"{pushed_ref(package)}^{{commit}}")
    except subprocess.CalledProcessError:
        return True
    if not ok("merge-base", "--is-ancestor", pushed, "HEAD"):
        return True
    if git("rev-list", "-n", "1", f"{pushed}..HEAD", "--", package):
        return True
    joined = git("rev-list", "-n", "1", "--merges", f"--grep=^git-subtree-dir: {package}$", f"{pushed}..HEAD")
    return bool(joined)


def run_push(
    checkout: Checkout,
    packages: Sequence[str],
    exclude: Sequence[str],
    no_check: bool,
    force: bool,
    dry_run: bool,
) -> int:
    """Check, then push the packages to the AUR, those with commits since their last push."""
    require("push", [("aurpublish", "aurpublish")])
    if not no_check:
        require("push (the checks)", [hook_runner_tool()])
    excluded = set()
    for name in exclude:
        folder = checkout.package_dir(name)
        if folder is None:
            raise SelectionError(f"Not a package: {name}")
        excluded.add(folder)
    selected = [p for p in checkout.select(packages, aur_only=True) if p not in excluded]
    pushing = [p for p in selected if force or push_needed(p)]
    unchanged = [p for p in selected if p not in pushing]
    if unchanged:
        plural = "" if len(unchanged) == 1 else "s"
        print(
            f"Nothing new since the last push of {len(unchanged)} package{plural} (--force pushes them anyway): "
            + " ".join(unchanged)
        )
    if not pushing:
        return 0
    if dry_run:
        print("Would check and push: " + " ".join(pushing))
        return 0
    if not no_check and checks.run_check(checkout, pushing, manual=False):
        return 1
    head = git("rev-parse", "HEAD")
    for package in pushing:
        if subprocess.run(["aurpublish", package], check=False).returncode:
            return 1
        git("update-ref", "-m", "aur-packages push", pushed_ref(package), head)
        # The tray's update list, which only the next check would clear otherwise; aurpublish pushes
        # HEAD's subtree, so HEAD's version
        state.forget_pushed(package, Srcinfo.parse(git("show", f"HEAD:{package}/.SRCINFO")).version())
    return 0


def merge_message(package: str, base: str, head: str, mainline: str, split: str) -> str:
    return (
        f"{package}: merge the earlier history of {base} on the AUR\n\n"
        f"- The AUR only accepts pushes on top of its history of {base} ({head[:7]}): the\n"
        "  package's history merges it, with the package's files unchanged\n\n"
        f"git-subtree-dir: {package}\ngit-subtree-mainline: {mainline}\ngit-subtree-split: {split}\n"
    )


def adopt_maintainers(package: str, head: str) -> None:
    """The AUR's maintainers as # Maintainer:, its other lines as # Contributor:, left to commit."""
    with tempfile.NamedTemporaryFile("w", suffix=".PKGBUILD") as previous:
        previous.write(git("show", f"{head}:PKGBUILD") + "\n")
        previous.flush()
        maintainers.adopt(package, previous.name)


def run_adopt(checkout: Checkout, packages: Sequence[str], dry_run: bool) -> int:
    """Merge the AUR's history of each package into the history push pushes, the package's subtree.

    A merge of the subtree's history and the AUR's head with the subtree's files, recorded like git
    subtree split --rejoin, so that later splits build on it.
    """
    if not packages:
        print("Usage: aur-packages adopt PACKAGE...", file=sys.stderr)
        return 2
    signing = sign()
    for package in checkout.select(packages, aur_only=True):
        base = Srcinfo.load(checkout.root / package).pkgbase
        head = aur_head(base)
        if head is None:
            print(f"{package}: couldn't reach the AUR", file=sys.stderr)
            return 1
        if not head:
            print(f"{package}: not on the AUR, nothing to adopt")
            continue
        git("fetch", "-q", aur_url(base), "master")
        split = git("subtree", "split", "-q", "-P", package)
        if ok("merge-base", "--is-ancestor", head, split):
            print(f"{package}: already on top of the AUR's {head[:7]}")
            continue
        if dry_run:
            print(f"{package}: would merge the AUR's {head[:7]} into its history")
            continue
        merge = git(
            "commit-tree", *signing, "-p", split, "-p", head,
            "-m", f"Merge the earlier history of {base} on the AUR", f"{split}^{{tree}}",
        )  # fmt: skip
        mainline = git("rev-parse", "HEAD")
        rejoin = git(
            "commit-tree", *signing, "-p", "HEAD", "-p", merge, "HEAD^{tree}",
            stdin=merge_message(package, base, head, mainline, merge),
        )  # fmt: skip
        git("merge", "-q", "--ff-only", rejoin)
        print(f"{package}: now on top of the AUR's {head[:7]}")
        # Its maintainers on the AUR as # Maintainer:, the AUR's other lines as # Contributor:
        adopt_maintainers(package, head)
    return 0


def readme_move_row(readme: Path, base: str, section: str, row: str) -> None:
    """Move the row of a package of local/ into the table under ### section, in alphabetical order."""
    lines = [
        line for line in readme.read_text().splitlines() if not line.startswith(f"| [{base}](local/{base}) |")
    ]
    start = lines.index(f"### {section}")
    table = []
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("### "):
            break
        if lines[index].startswith("| ["):
            table.append(index)
    if not table:
        raise SelectionError(f"README.md: no table under ### {section}")
    names = {index: lines[index][3:].split("]", 1)[0] for index in table}
    at = next((index for index in table if base.encode() <= names[index].encode()), table[-1] + 1)
    lines.insert(at, row)
    readme.write_text("\n".join(lines) + "\n")


def history_in(old: str, split: str, signing: list[str]) -> str:
    """The package's commits in local/ (split) on top of its history at the top level (old).

    The same changes, messages and authors; the commit of the move to local/ changes nothing in the
    package and is left out.
    """
    tip = old
    for commit in git("rev-list", "--reverse", split).splitlines():
        tree = git("rev-parse", f"{commit}^{{tree}}")
        if tip and git("rev-parse", f"{tip}^{{tree}}") == tree:
            continue
        author = git("log", "-1", "--format=%an%x00%ae%x00%ad", "--date=raw", commit).split("\0")
        env = {"GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1], "GIT_AUTHOR_DATE": author[2]}
        parents = ["-p", tip] if tip else []
        message = git("log", "-1", "--format=%B", commit)
        tip = git("commit-tree", *signing, *parents, tree, stdin=message + "\n", env=env)
    return tip


def run_publish(checkout: Checkout, packages: Sequence[str], section: str, adopt: bool, dry_run: bool) -> int:
    """Move packages of local/ to the top level, with the history push pushes, and commit.

    The package's earlier history at the top level, if it had one (the AUR's included), followed by
    its commits in local/. A plain git mv would leave it with a history starting at the move. Its
    row in README.md moves into the table of the section.
    """
    root = checkout.root
    readme = root / "README.md"
    if not packages:
        print("Usage: aur-packages publish [--section SECTION] [--adopt] PACKAGE...", file=sys.stderr)
        return 2
    if section == "Not on the AUR" or f"### {section}" not in readme.read_text().splitlines():
        print(f"README.md has no table of AUR packages under ### {section}", file=sys.stderr)
        return 1
    # The commits are made from the index, and README.md is rewritten
    if not ok("diff", "--cached", "--quiet") or not ok("diff", "--quiet", "--", "README.md"):
        print("Commit or unstage the staged changes and README.md's first", file=sys.stderr)
        return 1
    selected = checkout.select(packages)
    for folder in selected:
        name = folder.removeprefix("local/")
        if not folder.startswith("local/"):
            raise SelectionError(f"Not a package of local/: {folder}")
        if (root / name).exists():
            raise SelectionError(f"{name} exists at the top level already")
        if not ok("diff", "--quiet", "HEAD", "--", folder):
            raise SelectionError(f"{folder} has uncommitted changes")
    signing = sign()
    for folder in selected:
        name = folder.removeprefix("local/")
        base = Srcinfo.load(root / folder).pkgbase
        # Its earlier history at the top level: up to the last commit that had it there, the parent
        # of the one that moved it to local/
        old = ""
        if last := git("log", "-1", "--format=%H", "--", name):
            if not ok("cat-file", "-e", f"{last}:{name}/PKGBUILD"):
                last += "^"
            old = git("subtree", "split", "-q", "-P", name, last)
        split = git("subtree", "split", "-q", "-P", folder)
        head = aur_head(base)
        if head is None:
            print(f"{name}: couldn't reach the AUR", file=sys.stderr)
            return 1
        if dry_run:
            print(
                f"{name}: would move out of local/ into ### {section}"
                + (", merging the AUR's history" if head else "")
            )
            continue
        tip = history_in(old, split, signing)
        # The AUR only accepts it on top of its own history of the package
        if head and not (
            ok("cat-file", "-e", f"{head}^{{commit}}") and ok("merge-base", "--is-ancestor", head, tip)
        ):
            if not adopt:
                print(
                    f"{name}: the AUR's {base} ({head[:7]}) isn't part of its history; once it's yours on the "
                    "AUR, publish it with --adopt",
                    file=sys.stderr,
                )
                return 1
            git("fetch", "-q", aur_url(base), "master")
            tip = git(
                "commit-tree", *signing, "-p", tip, "-p", head,
                "-m", f"Merge the earlier history of {base} on the AUR", f"{tip}^{{tree}}",
            )  # fmt: skip
        else:
            head = ""
        git("mv", folder, name)
        readme_move_row(readme, base, section, checks.readme_row(Srcinfo.load(root / name), name))
        git("add", "README.md")
        if run_git("commit", "-q", "-m", f"{name}: move out of local/ to publish it on the AUR"):
            print(f"{name}: not moved, the checks failed", file=sys.stderr)
            git("mv", name, folder)
            git("restore", "--staged", "--worktree", "README.md")
            return 1
        move = git("rev-parse", "HEAD")
        earlier = "its earlier history at the top level, then " if old else ""
        message = (
            f"{name}: join its history for the AUR\n\n"
            f"- push pushes the package's history: {earlier}its\n  commits in local/\n\n"
            f"git-subtree-dir: {name}\ngit-subtree-mainline: {move}\ngit-subtree-split: {tip}\n"
        )
        rejoin = git("commit-tree", *signing, "-p", move, "-p", tip, f"{move}^{{tree}}", stdin=message)
        git("merge", "-q", "--ff-only", rejoin)
        count = int(git("rev-list", "--count", tip))
        print(
            f"{name}: moved out of local/ with a history of {count} commit{'' if count == 1 else 's'}; "
            f"push it with ./aur-packages push {name}"
        )
        if head:
            adopt_maintainers(name, head)
    return 0
