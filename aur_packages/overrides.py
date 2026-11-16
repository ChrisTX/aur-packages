"""The packages of overrides/: Arch Linux's packaging as subtrees, with changes of ours on top."""

import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from aur_packages.git import git, sign
from aur_packages.git import run as run_git
from aur_packages.repo import GITIGNORE, Checkout, SelectionError
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import require

# The repositories of Arch Linux, with their testing ones; the system's pacman.conf orders them
OFFICIAL = re.compile(r"^(core|extra|multilib)(-testing)?$")


def packaging_url(pkgbase: str) -> str:
    """Arch Linux's packaging repository of a pkgbase, named as devtools names GitLab's projects.

    With devtools' own function (gtk+ -> gtkplus, tree -> unix-tree); $AUR_PACKAGES_ARCH replaces
    the GitLab group, for the tests.
    """
    script = (
        "_DEVTOOLS_LIBRARY_DIR=/usr/share/devtools; source /usr/share/devtools/lib/api/gitlab.sh; "
        'gitlab_project_convert_name "$1"'
    )
    path = subprocess.run(
        ["bash", "-c", script, "bash", pkgbase], capture_output=True, text=True, check=True
    ).stdout.strip()
    group = os.environ.get("AUR_PACKAGES_ARCH", "https://gitlab.archlinux.org/archlinux/packaging/packages")
    return f"{group}/{path}.git"


def arch_version(pkgbase: str) -> tuple[str, str] | None:
    """The version pacman would install of a package and its repository, in pacman.conf's order.

    So on a system with the testing repositories, their version (core-testing before core).
    """
    repos = subprocess.run(["pacman-conf", "--repo-list"], capture_output=True, text=True, check=True).stdout
    for repo in (r for r in repos.split() if OFFICIAL.match(r)):
        info = subprocess.run(
            ["pacman", "-Si", f"{repo}/{pkgbase}"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        ).stdout
        if match := re.search(r"^Version\s*: (.+)$", info, re.MULTILINE):
            return match[1].strip(), repo
    return None


def vercmp(a: str, b: str) -> int:
    return int(subprocess.run(["vercmp", a, b], capture_output=True, text=True, check=True).stdout)


def override_status(checkout: Checkout, folder: str) -> int:
    """Print how an override compares with Arch Linux's package.

    0 while it's needed, 1 once Arch has caught up, 2 if Arch doesn't have the package.
    """
    srcinfo = Srcinfo.load(checkout.root / folder)
    name, ours = srcinfo.pkgbase, srcinfo.version()
    theirs = arch_version(name)
    if theirs is None:
        print(f"{name:<30} {ours}, not in Arch Linux's repositories")
        return 2
    version, repo = theirs
    if vercmp(version, ours) >= 0:
        print(f"{name:<30} {ours}, Arch Linux has {version} ({repo}): the override can go")
        return 1
    print(f"{name:<30} {ours}, Arch Linux has {version} ({repo})")
    return 0


def overrides_of(checkout: Checkout, packages: Sequence[str]) -> list[str]:
    selected = checkout.select(packages)
    for folder in selected:
        if not folder.startswith("overrides/"):
            raise SelectionError(f"Not an override: {folder}")
    return selected


def run_check(checkout: Checkout, packages: Sequence[str]) -> int:
    """Compare the overrides with Arch Linux, failing if Arch has caught up with one."""
    folders = (
        overrides_of(checkout, packages)
        if packages
        else [f for f in checkout.package_dirs() if f.startswith("overrides/")]
    )
    return 1 if any(override_status(checkout, f) == 1 for f in folders) else 0


GITIGNORE_ANNOTATION = """
[[annotations]]
path = ".gitignore"
SPDX-FileCopyrightText = "Arch Linux contributors"
SPDX-License-Identifier = "0BSD"
"""


def git_folders(srcinfo: Srcinfo) -> list[str]:
    """The folders of a package's git sources, which makepkg clones next to the PKGBUILD."""
    folders = []
    sources = [
        s for key, values in srcinfo.base.items() if re.fullmatch(r"source(_\w+)?", key) for s in values
    ]
    for source in sources:
        if "git+" not in source:
            continue
        name, separator, _ = source.partition("::")
        if not separator:
            name = re.split(r"[#?]", source, maxsplit=1)[0].rsplit("/", 1)[-1].removesuffix(".git")
        folders.append(name)
    return folders


def add_readme_row(readme: Path, base: str) -> None:
    """Insert the row of a new override into README.md's table of overrides, in alphabetical order."""
    lines = readme.read_text().splitlines()
    rows = [i for i, line in enumerate(lines) if line.startswith("| [") and "](overrides/" in line]
    if not rows:
        raise SelectionError(f"README.md: no table of overrides/ to add {base} to")
    names = {i: lines[i][3:].split("]", 1)[0] for i in rows}
    at = next((i for i in rows if base.encode() <= names[i].encode()), rows[-1] + 1)
    lines.insert(at, f"| [{base}](overrides/{base}) | TODO: what it changes | TODO: until when it's needed |")
    readme.write_text("\n".join(lines) + "\n")


def run_add(checkout: Checkout, name: str, dry_run: bool) -> int:
    """Import Arch Linux's packaging of a package as overrides/<pkgbase>, a subtree of it.

    Then prepare, without committing it, what the first commit of the changes adds besides them: the
    README.md row, the .gitignore with its REUSE annotation, and a pkgrel below Arch's next release.
    """
    require("overrides add", [("expac", "expac"), ("makepkg", "pacman")])
    base = subprocess.run(["expac", "-S", "%e", name], capture_output=True, text=True, check=False).stdout
    base = base.split("\n", 1)[0].strip()
    if not base:
        print(f"{name} isn't in Arch Linux's repositories", file=sys.stderr)
        return 1
    root = checkout.root
    folder = f"overrides/{base}"
    if any((root / f).exists() for f in (folder, base, f"local/{base}")):
        print(f"{base} is a package of this repository already", file=sys.stderr)
        return 1
    url = packaging_url(base)
    git("fetch", "-q", url, "main")
    version = Srcinfo.parse(git("show", "FETCH_HEAD:.SRCINFO")).version()
    if dry_run:
        print(f"Would add Arch Linux's packaging of {base} ({version}) from {url} as {folder}")
        return 0
    message = (
        f"overrides: add Arch Linux's {base} packaging\n\n"
        f"Arch Linux's packaging of {base} ({url.removeprefix('https://')}, {version}) as a subtree,\n"
        "the base of a local build with changes of ours."
    )
    git("subtree", "add", *sign(), "-q", "-P", folder, "FETCH_HEAD", "-m", message)

    # A pkgrel between Arch's and its next, so that Arch's next release replaces the override
    package = root / folder
    rel = Srcinfo.load(package).first("pkgrel")
    pkgbuild = package / "PKGBUILD"
    if "." in rel:
        print(
            f"pkgrel {rel} has a fraction already: set one between it and Arch's next by hand",
            file=sys.stderr,
        )
    else:
        comment = "# Below Arch Linux's next release, which replaces it: TODO, what the override changes"
        text = re.sub(
            rf"^pkgrel={re.escape(rel)}$",
            f"{comment}\npkgrel={rel}.1",
            pkgbuild.read_text(),
            count=1,
            flags=re.MULTILINE,
        )
        pkgbuild.write_text(text)
        srcinfo = subprocess.run(
            ["makepkg", "--printsrcinfo"], cwd=package, capture_output=True, text=True, check=True
        )
        (package / ".SRCINFO").write_text(srcinfo.stdout)
    folders = git_folders(Srcinfo.load(package))
    ignore = GITIGNORE + ("\n# Git sources\n" + "".join(f"{f}/\n" for f in folders) if folders else "")
    (package / ".gitignore").write_text(ignore)
    reuse = package / "REUSE.toml"
    if (
        reuse.exists()
        and '"\\.gitignore"' not in reuse.read_text()
        and '".gitignore"' not in reuse.read_text()
    ):
        reuse.write_text(reuse.read_text() + GITIGNORE_ANNOTATION)
    add_readme_row(root / "README.md", base)
    print(
        f"Added Arch Linux's packaging of {base} ({version}) as {folder}.\n"
        "Prepared for the first commit of your changes (not committed):\n"
        f"- {folder}/PKGBUILD: pkgrel {rel}.1, below Arch's next release; fill in its comment\n"
        f"- {folder}/.gitignore and its REUSE annotation\n"
        "- README.md: the row in the table of overrides; fill in what it changes and until when\n"
        "Then add your changes (patches with a comment linking their upstream issue or PR, and their REUSE\n"
        "annotations), update the checksums and .SRCINFO, and commit them as "
        f"upgpkg: {base} {version.rsplit('-', 1)[0]}-{rel}.1"
    )
    return 0


def run_pull(checkout: Checkout, packages: Sequence[str], dry_run: bool) -> int:
    """Merge Arch Linux's updates of the overrides' packaging into their subtrees."""
    if not packages:
        print("Usage: aur-packages overrides pull PACKAGE...", file=sys.stderr)
        return 2
    for folder in overrides_of(checkout, packages):
        base = folder.removeprefix("overrides/")
        url = packaging_url(base)
        git("fetch", "-q", url, "main")
        version = Srcinfo.parse(git("show", "FETCH_HEAD:.SRCINFO")).version()
        if dry_run:
            print(f"Would merge Arch Linux's {base} {version} into {folder}")
            continue
        head = git("rev-parse", "HEAD")
        message = f"overrides: merge Arch Linux's {base} {version}"
        if run_git("subtree", "pull", *sign(), "-q", "-P", folder, url, "main", "-m", message):
            print("Resolve the conflicts with our changes, then commit the merge", file=sys.stderr)
            return 1
        if git("rev-parse", "HEAD") == head:
            print(f"{folder} has Arch Linux's {base} {version} already")
        else:
            print(
                f"Merged Arch Linux's {base} {version}: bring the pkgrel below Arch's next release again, if it isn't"
            )
    return 0


def run_remove(checkout: Checkout, packages: Sequence[str], force: bool, dry_run: bool) -> int:
    """Remove overrides once Arch Linux has caught up with them (or with force), with their rows."""
    if not packages:
        print("Usage: aur-packages overrides remove [--force] PACKAGE...", file=sys.stderr)
        return 2
    readme = checkout.root / "README.md"
    for folder in overrides_of(checkout, packages):
        base = folder.removeprefix("overrides/")
        if override_status(checkout, folder) != 1 and not force:
            print(
                f"{base}: Arch Linux hasn't caught up with the override yet, --force removes it anyway",
                file=sys.stderr,
            )
            return 1
        if dry_run:
            print(f"Would remove {folder} and its README.md row")
            continue
        theirs = arch_version(base)
        git("rm", "-r", "-q", "--", folder)
        lines = readme.read_text().splitlines()
        readme.write_text(
            "\n".join(line for line in lines if not line.startswith(f"| [{base}](overrides/{base}) |")) + "\n"
        )
        git("add", "README.md")
        summary = f"overrides: drop {base}" + (f", Arch Linux has {theirs[0]}" if theirs else "")
        if run_git("commit", "-q", "-m", summary):
            return 1
        print(f"Removed {folder}")
        if (checkout.root / folder).is_dir():
            print(f"Untracked files are left in {folder}, e.g. downloads")
    return 0
