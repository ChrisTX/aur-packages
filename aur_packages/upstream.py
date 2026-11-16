"""The upstream issues, pull requests and commits the packages refer to, on GitHub.

For each one in the comments of a package's PKGBUILD: its state, and for a merged pull request or a
commit whether the upstream version the package builds contains it, so that its backport can go, or
else which release does. Contained means in the package's own repository at the tag or commit of
its source, or in a git submodule of that repository from the other one (SourcePawn in SourceMod).
"""

import json as jsonlib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
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


def sources(srcinfo: Srcinfo) -> dict[str, str]:
    """The package's sources on GitHub, in their order: owner/repository and its tag or commit,
    empty for a branch's head."""
    found: dict[str, str] = {}
    for entry in srcinfo.base.get("source", []):
        url = entry.split("::", 1)[-1]
        if match := re.search(rf"github\.com/({NAME})/({NAME}?)(\.git)?([/#?]|$)", url):
            ref = SOURCE_REF.search(url)
            found.setdefault(
                f"{match[1]}/{match[2]}", next((g for g in ref.groups() if g), "") if ref else ""
            )
    return found


def source(srcinfo: Srcinfo) -> tuple[str, str]:
    """owner/repository and the tag or commit of the package's first source on GitHub, empty if none."""
    return next(iter(sources(srcinfo).items()), ("", ""))


def text_references(text: str, own: str) -> list[Reference]:
    """The references in a text, in their order."""
    found: list[Reference] = []
    text = URL.sub(lambda m: f"{m[1]}#{m[2]}", text)
    for match in SHORT.finditer(text):
        found.append(Reference(match[1], number=int(match[2])))
    if own:
        for match in BARE.finditer(SHORT.sub("", text)):
            found.append(Reference(own, number=int(match[1])))
    for match in COMMIT.finditer(text):
        found.append(Reference(match[1], commit=match[2]))
    return found


def references(pkgbuild: str, own: str) -> list[Reference]:
    """The references in the comments of a PKGBUILD, each once, in their order."""
    found: list[Reference] = []
    for line in pkgbuild.splitlines():
        comment = line.split("#", 1)[1] if line.lstrip().startswith("#") else ""
        if not comment and " # " in line:
            comment = line.split(" # ", 1)[1]
        found += text_references(comment, own)
    return list(dict.fromkeys(found))


# What a change the package carries is to upstream, in a comment right above it:
#   # upstream: backport owner/repo#1     a fix of upstream's, until the packaged version has it
#   # upstream: pending owner/repo#1      our own proposal, the same
#   # upstream: workaround owner/repo#1   for an upstream issue, until it's closed
#   # upstream: none <why>                ours only, e.g. Arch's system libraries
VERBS = ("backport", "pending", "workaround", "none")
DIRECTIVE = re.compile(r"^\s*#\s*upstream:\s*(.*)$")
MISSING = (
    "a patch without '# upstream: backport|pending|workaround REFERENCE' or "
    "'# upstream: none REASON' in the comment right above it"
)
# The lines that apply a patch file, which need a directive
PATCH_LINE = re.compile(r"^\s*(?:patch\b|git(?:\s+-C\s+\S+)*\s+(?:apply|am)\b)")


@dataclass(frozen=True)
class Directive:
    line: int
    verb: str
    references: tuple[Reference, ...]
    text: str


def directive(number: int, text: str, own: str) -> tuple[Directive | None, str]:
    """A directive's line parsed, or what's wrong with it."""
    # The verb, then the references or the reason, e.g. after a comma
    match = re.match(r"(\S*?)[,:]?(?:\s+|$)(.*)", text.strip())
    verb, rest = (match[1], match[2].strip()) if match else ("", "")
    if verb not in VERBS:
        return None, f"upstream: {verb or '(nothing)'}: the verb is one of {', '.join(VERBS)}"
    found = tuple(dict.fromkeys(text_references(rest, own)))
    if verb == "none":
        if not rest:
            return None, "upstream: none needs the reason, e.g. 'upstream: none, system libraries'"
        return Directive(number, verb, (), rest), ""
    if not found:
        return None, f"upstream: {verb} needs a reference: owner/repo#1, its URL or owner/repo@commit"
    return Directive(number, verb, found, rest), ""


def directives(pkgbuild: str, own: str) -> tuple[list[Directive], list[tuple[int, str]]]:
    """The directives of a PKGBUILD, and its problems as (line, message): a malformed directive, and
    a patch file applied without a directive in the comment right above it."""
    found: list[Directive] = []
    problems: list[tuple[int, str]] = []
    above = False  # whether the comment block right above has a directive
    for number, line in enumerate(pkgbuild.splitlines(), 1):
        if line.lstrip().startswith("#"):
            if match := DIRECTIVE.match(line):
                above = True
                parsed, problem = directive(number, match[1], own)
                if parsed is not None:
                    found.append(parsed)
                else:
                    problems.append((number, problem))
            continue
        if PATCH_LINE.match(line) and not above:
            problems.append((number, MISSING))
        above = False
    return found, problems


# For the daily check (notes): the answers that can't change anymore, kept across checks, and the
# requests that failed in this one
persistent: dict[str, Any] | None = None
failed: list[str] = []


def final(url: str, data: Any) -> dict[str, Any] | None:
    """What of an answer of GitHub's API can't change anymore, to keep; None if it can.

    Whether a number is an issue or a pull request, a closed pull request (merged or not), and that a
    tag or commit contains a commit (the packaged versions are tags or commits).
    """
    if not isinstance(data, dict):
        return None
    if re.search(r"/issues/[0-9]+$", url):
        return {"pull_request": data["pull_request"]} if "pull_request" in data else {}
    if re.search(r"/pulls/[0-9]+$", url) and data.get("state") == "closed":
        return {key: data.get(key) for key in ("state", "merged", "merge_commit_sha", "draft")}
    if "/compare/" in url and data.get("status") in ("ahead", "identical"):
        return {"status": data["status"]}
    return None


@cache
def json(url: str) -> Any:
    if persistent is not None and url in persistent:
        return persistent[url]
    data = request_json(url)
    if data is None:
        failed.append(url)
    elif persistent is not None and (kept := final(url, data)) is not None:
        persistent[url] = kept
    return data


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


def short(version: str) -> str:
    return version[:12] if re.fullmatch(r"[0-9a-f]{40}", version) else version


def released(
    reference: Reference, commit: str, own: str, version: str, others: dict[str, str] | None = None
) -> tuple[str, bool]:
    """Where a merged commit is released: in the packaged version, or the newest release that has it.

    The packaged version of the reference's repository: the package's own (its first source), another
    of its sources (others, owner/repository and its tag or commit), or a git submodule of its own.
    """
    pinned = {name.lower(): ref for name, ref in (others or {}).items()}.get(reference.repository.lower())
    if pinned and reference.repository.lower() != own.lower():
        own, version = reference.repository, pinned
    shown = short(version)
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


def state(
    reference: Reference, own: str, version: str, others: dict[str, str] | None = None
) -> tuple[str, bool]:
    """A reference's state, and whether the packaged version contains its fix."""
    if reference.commit is not None:
        where, packaged = released(reference, reference.commit, own, version, others)
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
        where, packaged = released(reference, str(pull.get("merge_commit_sha")), own, version, others)
        return f"merged, {where}", packaged
    if pull.get("state") == "closed":
        return "closed, not merged", False
    return "open (draft)" if pull.get("draft") else "open", False


def note(text: str, packaged: bool) -> str | None:
    """What a directive's reference in this state wants done, if anything."""
    if packaged:
        return f"{text}: check whether what we carry for it can go"
    if text == "closed, not merged":
        return "closed without being merged: check what we carry for it"
    if text.startswith("issue closed"):
        return f"{text}: check whether what we carry for it can go"
    return None


def url(reference: Reference) -> str:
    if reference.number is None:
        return f"https://github.com/{reference.repository}/commit/{reference.commit}"
    return f"https://github.com/{reference.repository}/issues/{reference.number}"


def package_directives(checkout: Checkout, name: str) -> tuple[list[Directive], str, str, dict[str, str]]:
    """A package's directives, its own repository and version, and its sources on GitHub."""
    found = sources(Srcinfo.load(checkout.root / name))
    own, version = next(iter(found.items()), ("", ""))
    parsed, _ = directives((checkout.root / name / "PKGBUILD").read_text(), own)
    return parsed, own, version, found


def notes(checkout: Checkout, cache_file: Path) -> list[dict[str, str]] | None:
    """What wants something done, for the daily check, from the # upstream: directives: a reference
    the packaged version contains (a merged pull request or a commit), a pull request closed without
    being merged, a closed issue. None if a request failed, e.g. at GitHub's rate limit, so the notes
    of the last check stay.

    Asks only about what can still change: the answers that can't are kept in cache_file.
    """
    global persistent
    try:
        loaded = jsonlib.loads(cache_file.read_text()) if cache_file.exists() else {}
    except jsonlib.JSONDecodeError:
        loaded = {}
    persistent = loaded if isinstance(loaded, dict) else {}
    failed.clear()
    json.cache_clear()
    found = []
    try:
        for name in checkout.package_dirs():
            parsed, own, version, others = package_directives(checkout, name)
            for entry in parsed:
                for reference in entry.references:
                    if message := note(*state(reference, own, version, others)):
                        found.append(
                            {"folder": name, "reference": str(reference), "url": url(reference),
                             "message": f"{entry.verb}: {message}"}
                        )  # fmt: skip
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(jsonlib.dumps(persistent, indent=1, sort_keys=True) + "\n")
    finally:
        persistent = None
        json.cache_clear()
    return None if failed else found


def run_check(checkout: Checkout, paths: Sequence[str]) -> int:
    """That every patch a PKGBUILD applies has a well-formed directive right above it (the hook)."""
    status = 0
    names = [path.removesuffix("/PKGBUILD") for path in paths]
    for name in checkout.select(list(dict.fromkeys(names))):
        if name.startswith("overrides/"):
            continue
        own = source(Srcinfo.load(checkout.root / name))[0]
        _, problems = directives((checkout.root / name / "PKGBUILD").read_text(), own)
        for number, problem in problems:
            print(f"{name}/PKGBUILD:{number}: {problem}", file=sys.stderr)
            status = 1
    return status


def run_upstream(checkout: Checkout, packages: Sequence[str], check: bool = False) -> int:
    """Show the upstream references of the packages, with the verb of their directive, and what the
    directives' references want done; with check, only check the directives, offline."""
    if check:
        return run_check(checkout, packages)
    wanted = []
    for name in checkout.select(packages):
        parsed, own, version, others = package_directives(checkout, name)
        verbs = {reference: entry.verb for entry in parsed for reference in entry.references}
        for reference in references((checkout.root / name / "PKGBUILD").read_text(), own):
            text, packaged = state(reference, own, version, others)
            verb = verbs.get(reference, "")
            print(f"{name:<38} {reference!s:<44} {verb:<10} {text}")
            if verb and (message := note(text, packaged)):
                wanted.append(f"{name}: {reference} ({verb}): {message}")
    if wanted:
        sys.stdout.flush()
        print("\nWhat the upstream: directives want done:", file=sys.stderr)
        for entry in wanted:
            print(f"  {entry}", file=sys.stderr)
    return 0
