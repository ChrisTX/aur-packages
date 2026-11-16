"""The checks the hooks run on every commit: quoting, pins, readme, maintainers and sync."""

import json
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from aur_packages import git, keys, pins
from aur_packages import maintainers as maintainer_lines
from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import hook_runner, hook_runner_tool, require


def strip_pkgbuild(names: Sequence[str]) -> list[str]:
    """Packages given as their folders, or as their PKGBUILDs, as the hooks pass them."""
    return [name.removesuffix("/PKGBUILD") for name in names]


# The metadata arrays of a PKGBUILD whose quoting CONTRIBUTING.md sets, per architecture as well
METADATA_ARRAYS = re.compile(
    r"^(arch|license|groups|depends|makedepends|checkdepends|optdepends|provides|conflicts|replaces"
    r"|options|backup|noextract|validpgpkeys)(_.+)?$"
)
BARE = re.compile(r"^!?[A-Za-z0-9._+@/=:,-]+$")


def assignments(node: Any) -> Iterator[dict[str, Any]]:
    """The assignments anywhere in shfmt's syntax tree, so package functions count as well."""
    if isinstance(node, dict):
        yield from node.get("Assigns") or []
        for value in node.values():
            yield from assignments(value)
    elif isinstance(node, list):
        for value in node:
            yield from assignments(value)


def quoting_problem(parts: list[dict[str, Any]]) -> str | None:
    """What's wrong with the quoting of an array's element, made of these parts, if anything."""
    if len(parts) > 1:
        if any(part.get("Type") in ("SglQuoted", "DblQuoted") for part in parts):
            return "a word quoted in part, double-quote it as a whole"
        return None
    part = parts[0]
    if part.get("Type") == "SglQuoted":
        value = part.get("Value", "")
        return f"'{value}' is a plain word, write it unquoted" if BARE.match(value) else None
    if part.get("Type") == "DblQuoted":
        inner = part.get("Parts") or []
        if not all(p.get("Type") == "Lit" for p in inner):
            return None
        text = "".join(p.get("Value", "") for p in inner)
        if BARE.match(text):
            return f'"{text}" is a plain word, write it unquoted'
        if "'" in text:
            return None
        return f'"{text}" has nothing that expands, single-quote it'
    return None


def quoting_findings(pkgbuild: Path, label: str) -> list[str]:
    """The quoting problems of the metadata arrays of a PKGBUILD, as file:line:column: messages."""
    tree = json.loads(
        subprocess.run(
            ["shfmt", "-ln", "bash", "--to-json"],
            input=pkgbuild.read_text(),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    findings: list[tuple[int, int, str]] = []
    for assign in assignments(tree):
        name = (assign.get("Name") or {}).get("Value", "")
        array = assign.get("Array")
        if array is None or not METADATA_ARRAYS.match(name):
            continue
        # An empty array (depends=()) has no elements at all
        for element in array.get("Elems") or []:
            parts = (element.get("Value") or {}).get("Parts") or []
            if parts and (problem := quoting_problem(parts)):
                position = element.get("Pos") or {}
                line, column = position.get("Line", 0), position.get("Col", 0)
                findings.append((line, column, f"{label}:{line}:{column}: {name}: {problem}"))
    return [finding for *_, finding in sorted(findings)]


def run_quoting(checkout: Checkout, packages: Sequence[str]) -> int:
    """The quoting of the metadata arrays against CONTRIBUTING.md, from shfmt's syntax tree."""
    require("quoting", [("shfmt", "shfmt")])
    status = 0
    for package in checkout.select(strip_pkgbuild(packages)):
        for finding in quoting_findings(checkout.root / package / "PKGBUILD", f"{package}/PKGBUILD"):
            print(finding, file=sys.stderr)
            status = 1
    return status


# A row of README.md's tables of the packages: its link, the AUR's or a folder's
README_ROW = re.compile(
    r"^\| \[([^]]+)\]\((https://aur\.archlinux\.org/(packages|pkgbase)/|local/|overrides/)"
)


def readme_row(srcinfo: Srcinfo, folder: str) -> str:
    """The row README.md has for a package in a folder, for local/ and overrides/ its start only.

    The link (the AUR's, or the folder for local/ and overrides/), the packages of a split package,
    its pkgdesc and the AUR version badge; the columns after the description of local/ (why) and
    those of overrides/ are free text.
    """
    base = srcinfo.pkgbase
    if folder.startswith("overrides/"):
        return f"| [{base}](overrides/{base}) | "
    if folder.startswith("local/"):
        return f"| [{base}](local/{base}) | {srcinfo.pkgdesc()} | "
    names = srcinfo.pkgnames()
    first = names[0]
    if names == [base]:
        link = f"[{base}](https://aur.archlinux.org/packages/{base})"
    else:
        listed = ", ".join(f"`{name}`" for name in names)
        link = f"[{base}](https://aur.archlinux.org/pkgbase/{base}) ({listed})"
    badge = (
        f"[![AUR version](https://img.shields.io/aur/version/{first}?label=)]"
        f"(https://aur.archlinux.org/packages/{first})"
    )
    return f"| {link} | {srcinfo.pkgdesc()} | {badge} |"


def run_readme(checkout: Checkout) -> int:
    """README.md's tables against the packages: exactly one row each, and no row of no package."""
    status = 0
    rows: dict[str, str] = {}
    for line in (checkout.root / "README.md").read_text().splitlines():
        if match := README_ROW.match(line):
            if match[1] in rows:
                print(f"README.md: more than one row for {match[1]}")
                status = 1
            rows[match[1]] = line
    seen = set()
    for folder in checkout.package_dirs():
        srcinfo = Srcinfo.load(checkout.root / folder)
        seen.add(srcinfo.pkgbase)
        expected = readme_row(srcinfo, folder)
        row = rows.get(srcinfo.pkgbase)
        if row is None:
            print(f"README.md: no row for {folder}, which should start with:\n  {expected}")
            status = 1
        elif row != expected and ("/" not in folder or not row.startswith(expected)):
            print(f"README.md: the row of {folder} should be (or start with):\n  {expected}\nnot:\n  {row}")
            status = 1
    for base in rows:
        if base not in seen:
            print(f"README.md: a row for {base}, which isn't a package")
            status = 1
    return status


def run_maintainers(checkout: Checkout, packages: Sequence[str], aur: bool, as_json: bool) -> int:
    """The # Maintainer: and # Contributor: lines, or with aur against the AUR's maintainers.

    The packages of overrides/ keep Arch Linux's lines, so they're left out.
    """
    folders = [p for p in checkout.select(strip_pkgbuild(packages)) if not p.startswith("overrides/")]
    if not folders:
        return 0
    if not aur:
        return maintainer_lines.check(folders, author=False)
    found = maintainer_lines.notes(folders)
    if as_json:
        print(json.dumps(found))
        return 0
    for note in found:
        print(f"{note['folder']}: {note['message']}")
    return 1 if found else 0


# The files every package copies from templates/package, so it can be checked on its own
TEMPLATE_FILES = (".editorconfig", ".pre-commit-config.yaml", ".typos.toml")


def run_sync(checkout: Checkout, packages: Sequence[str], dry_run: bool) -> int:
    """Copy templates/package into the packages and write the top level's configuration from it.

    With dry_run, only report the files that differ, and fail then. Arch Linux's packages in
    overrides/ keep their own files, unless an override has copies of its own.
    """
    root = checkout.root
    template = root / "templates" / "package"

    def content(*files: Path) -> str:
        return "".join(file.read_text() for file in files).rstrip("\n") + "\n"

    wanted: list[tuple[Path, str]] = []
    for package in checkout.select(packages):
        if package.startswith("overrides/") and not (root / package / ".pre-commit-config.yaml").exists():
            continue
        wanted += [(root / package / name, content(template / name)) for name in TEMPLATE_FILES]
    wanted += [
        (root / ".editorconfig", content(template / ".editorconfig")),
        (root / ".typos.toml", content(template / ".typos.toml")),
        (
            root / ".pre-commit-config.yaml",
            content(template / ".pre-commit-config.yaml", root / "templates" / "root-hooks.yaml"),
        ),
    ]
    status = 0
    for path, text in wanted:
        if path.exists() and path.read_text() == text:
            continue
        name = path.relative_to(root)
        if dry_run:
            print(f"Differs from the template: {name}", file=sys.stderr)
            status = 1
        else:
            path.write_text(text)
            print(f"Updated {name}")
    return status


def run_package_hooks(packages: Sequence[str], stage: list[str]) -> int:
    """The hooks of the packages' own .pre-commit-config.yaml on their files."""
    runner = hook_runner()
    if runner == "prek":
        # prek's workspace has a project per package folder, named package/
        files = git_files(packages)
        return subprocess.run(
            ["prek", "run", "--refresh", *stage, *(f"{p}/" for p in packages), "--files", *files], check=False
        ).returncode
    # pre-commit has no workspaces: one package after the other, with its configuration
    status = 0
    for package in packages:
        command = ["pre-commit", "run", *stage, "--config", f"{package}/.pre-commit-config.yaml"]
        status |= subprocess.run([*command, "--files", *git_files([package])], check=False).returncode
    return status


def git_files(packages: Sequence[str]) -> list[str]:
    """The files of packages, tracked or new, without the ignored ones (downloads, builds): a new
    package's files are checked before they're added."""
    return git.paths("ls-files", "--cached", "--others", "--exclude-standard", "--", *packages)


def run_check(checkout: Checkout, packages: Sequence[str], manual: bool) -> int:
    """The checks of .pre-commit-config.yaml, with manual also those that only run on request.

    Packages given, only theirs: the hooks of their own .pre-commit-config.yaml, and those of the
    top level that check single packages (templates, quoting, pins, maintainers), not for overrides/
    where the hooks leave them out either. The top level's copies of the package hooks would check
    the same files again, and its other hooks check every package.
    """
    require("check", [hook_runner_tool()])
    runner = hook_runner()
    if not packages:
        refresh = ["--refresh"] if runner == "prek" else []
        status = subprocess.run([runner, "run", *refresh, "--all-files"], check=False).returncode
        if manual:
            stage = ["--hook-stage", "manual"]
            status |= subprocess.run([runner, "run", *refresh, *stage, "--all-files"], check=False).returncode
        return 1 if status else 0
    selected = checkout.select(packages)
    # Arch Linux's packages in overrides/ have no configuration of their own, unless an override got one
    configured = [p for p in selected if (checkout.root / p / ".pre-commit-config.yaml").exists()]
    status = run_package_hooks(configured, []) if configured else 0
    if manual and configured:
        status |= run_package_hooks(configured, ["--hook-stage", "manual"])
    status |= run_sync(checkout, selected, dry_run=True)
    status |= keys.run_keys(checkout, selected, fetch=False)
    ours = [p for p in selected if not p.startswith("overrides/")]
    if ours:
        status |= run_quoting(checkout, ours)
        status |= pins.run_pins(checkout, ours)
        status |= run_maintainers(checkout, ours, aur=False, as_json=False)
    return 1 if status else 0
