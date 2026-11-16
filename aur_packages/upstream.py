"""The upstream issues, pull requests and commits the packages refer to, on GitHub.

For each one in the comments of a package's PKGBUILD: its state, and for a merged pull request or a
commit whether the upstream version the package builds contains it, so that its backport can go, or
else which release does. Contained means in the package's own repository at the tag or commit of
its source, or in a git submodule of that repository from the other one (SourcePawn in SourceMod).
"""

import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo
from aur_packages.web import request, request_json

API = "https://api.github.com/repos"
NAME = r"[A-Za-z0-9_.-]+"
# https://github.com/owner/repo/pull/1 or /issues/1, owner/repo#1, a bare #1 (the package's own
# repository), and commits as owner/repo@0e3f7dbc
URL = re.compile(rf"https://github\.com/({NAME}/{NAME})/(?:pull|issues)/([0-9]+)")
SHORT = re.compile(rf"(?<![\w./-])({NAME}/{NAME})#([0-9]+)\b")
BARE = re.compile(r"(?<![\w/#])#([0-9]+)\b")
COMMIT = re.compile(rf"(?<![\w./-])({NAME}/{NAME})@([0-9a-f]{{7,40}})\b")
# The tag, commit or branch of a source on GitHub: a git checkout or an archive
SOURCE_REF = re.compile(r"#(?:tag|commit|branch)=([^?]+)|/archive/(?:refs/tags/)?(.+?)\.(?:tar\.gz|zip)$")


@dataclass(frozen=True)
class Reference:
    repository: str
    number: int | None = None
    commit: str | None = None

    def __str__(self) -> str:
        return (
            f"{self.repository}#{self.number}"
            if self.number is not None
            else f"{self.repository}@{self.commit}"
        )


def source(srcinfo: Srcinfo) -> tuple[str, str]:
    """owner/repository and the tag or commit of the package's first source on GitHub, empty if none."""
    for entry in srcinfo.base.get("source", []):
        url = entry.split("::", 1)[-1]
        if match := re.search(rf"github\.com/({NAME})/({NAME}?)(\.git)?([/#?]|$)", url):
            ref = SOURCE_REF.search(url)
            return f"{match[1]}/{match[2]}", next((g for g in ref.groups() if g), "") if ref else ""
    return "", ""


def references(pkgbuild: str, own: str) -> list[Reference]:
    """The references in the comments of a PKGBUILD, each once, in their order."""
    found: list[Reference] = []
    for line in pkgbuild.splitlines():
        comment = line.split("#", 1)[1] if line.lstrip().startswith("#") else ""
        if not comment and " # " in line:
            comment = line.split(" # ", 1)[1]
        text = URL.sub(lambda m: f"{m[1]}#{m[2]}", comment)
        for match in SHORT.finditer(text):
            found.append(Reference(match[1], number=int(match[2])))
        if own:
            for match in BARE.finditer(SHORT.sub("", text)):
                found.append(Reference(own, number=int(match[1])))
        for match in COMMIT.finditer(text):
            found.append(Reference(match[1], commit=match[2]))
    return list(dict.fromkeys(found))


@cache
def json(url: str) -> Any:
    return request_json(url)


def contains(repository: str, commit: str, ref: str) -> bool | None:
    """Whether a ref of a repository contains a commit, None if GitHub can't tell."""
    comparison = json(f"{API}/{repository}/compare/{commit}...{ref}")
    if not isinstance(comparison, dict):
        return None
    return comparison.get("status") in ("ahead", "identical")


@cache
def submodule(repository: str, ref: str, other: str) -> str:
    """The commit a repository's git submodule of another repository has at a ref, empty if none."""
    gitmodules = request(f"https://raw.githubusercontent.com/{repository}/{ref}/.gitmodules")
    for section in (gitmodules or b"").decode(errors="replace").split("[submodule")[1:]:
        path = re.search(r"^\s*path\s*=\s*(\S+)", section, re.MULTILINE)
        url = re.search(r"^\s*url\s*=\s*(\S+)", section, re.MULTILINE)
        if (
            path
            and url
            and re.search(rf"github\.com[/:]{re.escape(other)}(\.git)?/?$", url[1], re.IGNORECASE)
        ):
            contents = json(f"{API}/{repository}/contents/{path[1]}?ref={ref}")
            if isinstance(contents, dict) and contents.get("type") == "submodule":
                return str(contents.get("sha", ""))
    return ""


@cache
def latest_release(repository: str) -> str:
    """The tag of a repository's newest release, prereleases included, else of its newest tag."""
    releases = json(f"{API}/{repository}/releases?per_page=1")
    if isinstance(releases, list) and releases:
        return str(releases[0].get("tag_name", ""))
    tags = json(f"{API}/{repository}/tags?per_page=1")
    return str(tags[0].get("name", "")) if isinstance(tags, list) and tags else ""


def released(reference: Reference, commit: str, own: str, version: str) -> tuple[str, bool]:
    """Where a merged commit is released: in the packaged version, or the newest release that has it."""
    shown = version[:12] if re.fullmatch(r"[0-9a-f]{40}", version) else version
    if own and version:
        if reference.repository.lower() == own.lower():
            packaged: str | None = version
        else:
            packaged = submodule(own, version, reference.repository) or None
        if packaged is not None:
            inside = contains(reference.repository, commit, packaged)
            if inside:
                return f"in the packaged {shown}", True
            if inside is False and reference.repository.lower() != own.lower():
                # The submodule of a newer release of the package
                newest = latest_release(own)
                if (
                    newest
                    and newest != version
                    and (pinned := submodule(own, newest, reference.repository))
                    and contains(reference.repository, commit, pinned)
                ):
                    return f"not in the packaged {shown}, in {newest}", False
                return f"not in the packaged {shown}", False
    newest = latest_release(reference.repository)
    if newest and contains(reference.repository, commit, newest):
        prefix = (
            f"not in the packaged {shown}, " if reference.repository.lower() == (own or "").lower() else ""
        )
        return f"{prefix}in {newest}", False
    return "not released yet", False


def state(reference: Reference, own: str, version: str) -> tuple[str, bool]:
    """A reference's state, and whether the packaged version contains its fix."""
    if reference.commit is not None:
        where, packaged = released(reference, reference.commit, own, version)
        return f"commit, {where}", packaged
    issue = json(f"{API}/{reference.repository}/issues/{reference.number}")
    if not isinstance(issue, dict):
        return "not found", False
    if "pull_request" not in issue:
        reason = f" ({issue['state_reason'].replace('_', ' ')})" if issue.get("state_reason") else ""
        return f"issue {issue.get('state', '?')}{reason}", False
    pull = json(f"{API}/{reference.repository}/pulls/{reference.number}")
    if not isinstance(pull, dict):
        return "not found", False
    if pull.get("merged"):
        where, packaged = released(reference, str(pull.get("merge_commit_sha")), own, version)
        return f"merged, {where}", packaged
    if pull.get("state") == "closed":
        return "closed, not merged", False
    return "open (draft)" if pull.get("draft") else "open", False


def run_upstream(checkout: Checkout, packages: Sequence[str]) -> int:
    """Show the upstream references of the packages, and those the packaged versions contain."""
    contained = []
    for name in checkout.select(packages):
        own, version = source(Srcinfo.load(checkout.root / name))
        for reference in references((checkout.root / name / "PKGBUILD").read_text(), own):
            text, packaged = state(reference, own, version)
            print(f"{name:<38} {reference!s:<44} {text}")
            if packaged:
                contained.append(f"{name}: {reference}")
    if contained:
        sys.stdout.flush()
        print(
            "\nIn the packaged versions already: check whether what refers to them, e.g. a backport, can go:",
            file=sys.stderr,
        )
        for entry in contained:
            print(f"  {entry}", file=sys.stderr)
    return 0
