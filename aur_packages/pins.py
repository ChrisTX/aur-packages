"""The pins of the PKGBUILDs: commits and other values a version names, offline and online.

pins (offline, the hook) checks that a _commit is the commit a pkgver like git describe's names;
pins --online looks up what every pin should be, and --update rewrites the stale ones.
"""

import io
import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from aur_packages.git import paths
from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import require
from aur_packages.updates import github_token


def pin_value(pkgbuild: Path, name: str) -> str:
    """The value a PKGBUILD assigns to a variable on a line of its own, quoted or not."""
    pattern = re.compile(rf"^{re.escape(name)}=[\"']?([^\"']*)[\"']?$")
    for line in pkgbuild.read_text().splitlines():
        if match := pattern.match(line):
            return match[1]
    return ""


def set_pin(pkgbuild: Path, name: str, value: str) -> None:
    """Set a pinned variable in a PKGBUILD, and pkgrel to 1 with pkgver."""
    text = re.sub(
        rf"^({re.escape(name)}=[\"']?)[^\"']*([\"']?)$",
        rf"\g<1>{value}\g<2>",
        pkgbuild.read_text(),
        flags=re.MULTILINE,
    )
    if name == "pkgver":
        text = re.sub(r"^pkgrel=.*$", "pkgrel=1", text, flags=re.MULTILINE)
    pkgbuild.write_text(text)


def short_pin(value: str) -> str:
    """Commits in full are shown as 12 characters."""
    return value[:12] if re.fullmatch(r"[0-9a-f]{40}", value) else value


def request(url: str, attempts: int = 3) -> bytes | None:
    """The body of a URL, None if it fails; GitHub's API with the token of github_token, for its rate
    limit rather than the 60 requests an hour without one. Gives up on a stalled connection and tries
    again, instead of waiting forever."""
    req = urllib.request.Request(url, headers={"User-Agent": "aur-packages"})
    if url.startswith("https://api.github.com/") and (token := github_token()):
        req.add_header("Authorization", f"Bearer {token}")
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError:
            return None
        except OSError:
            if attempt == attempts - 1:
                return None
    return None


def request_json(url: str) -> Any:
    body = request(url)
    try:
        return json.loads(body) if body is not None else None
    except json.JSONDecodeError:
        return None


def array_first(pkgbuild: str, name: str) -> str:
    """The first element of an array a PKGBUILD assigns, on one line or several."""
    if match := re.search(rf"^{re.escape(name)}=\(\s*([^\s)]+)", pkgbuild, re.MULTILINE):
        return match[1].strip("'\"")
    return ""


def array(pkgbuild: str, name: str) -> list[str]:
    """The elements of an array a PKGBUILD assigns, without expansions."""
    if match := re.search(rf"^{re.escape(name)}=\(([^)]*)\)", pkgbuild, re.MULTILINE):
        return [word.strip("'\"") for word in match[1].split()]
    return []


def github_repository(srcinfo: Srcinfo) -> str:
    """owner/repository of the first source on GitHub, a git checkout or an archive."""
    for source in srcinfo.base.get("source", []):
        if match := re.search(r"github\.com/([^/]+)/([^/#?]+?)(\.git)?([/#?]|$)", source):
            return f"{match[1]}/{match[2]}"
    return ""


def nuget_commit(package: Path, pkgbuild: str, version: str) -> str:
    """The upstream commit a version was published from, best effort: the repository commit of the
    NuGet package's nuspec, by the package's NuGet id (_nugetid, else the first of _packages, else the
    .nvchecker.toml's packageid)."""
    nuget_id = pin_value(package / "PKGBUILD", "_nugetid") or array_first(pkgbuild, "_packages")
    nvchecker = package / ".nvchecker.toml"
    if (
        not nuget_id
        and nvchecker.exists()
        and (match := re.search(r"packageid:([^&\"]+)", nvchecker.read_text()))
    ):
        nuget_id = match[1]
    if not nuget_id:
        return ""
    lower = nuget_id.lower()
    base = f"https://api.nuget.org/v3-flatcontainer/{lower}/{version}"
    # The flat container serves the nuspec on its own; else from the whole package
    nuspec = request(f"{base}/{lower}.nuspec")
    if nuspec is None and (nupkg := request(f"{base}/{lower}.{version}.nupkg")) is not None:
        try:
            with zipfile.ZipFile(io.BytesIO(nupkg)) as archive:
                name = next((n for n in archive.namelist() if n.endswith(".nuspec")), None)
                nuspec = archive.read(name) if name else None
        except zipfile.BadZipFile:
            nuspec = None
    match = re.search(r'commit="([0-9a-f]{40})"', (nuspec or b"").decode(errors="replace"), re.IGNORECASE)
    return match[1] if match else ""


def described_commit(srcinfo: Srcinfo, version: str) -> str:
    """The full commit a pkgver like git describe's names (….r84.g5b0aa72), on GitHub."""
    match = re.search(r"\.g([0-9a-f]{7,40})$", version)
    repository = github_repository(srcinfo)
    if not match or not repository:
        return ""
    commit = request_json(f"https://api.github.com/repos/{repository}/commits/{match[1]}")
    return commit.get("sha", "") if isinstance(commit, dict) else ""


def vmr_commit(version: str, path: str) -> str:
    """The commit of one of the repositories of .NET's VMR (dotnet/dotnet) a release was built from."""
    manifest = request_json(
        f"https://raw.githubusercontent.com/dotnet/dotnet/v{version}/src/source-manifest.json"
    )
    repositories = manifest.get("repositories", []) if isinstance(manifest, dict) else []
    return next((str(r.get("commitSha", "")) for r in repositories if r.get("path") == path), "")


def file_value(url: str, pattern: str) -> str:
    """The first group of a pattern in a file, e.g. a commit in the CI workflow of a release."""
    body = request(url)
    match = re.search(pattern, (body or b"").decode(errors="replace"), re.MULTILINE)
    return match[1] if match else ""


def branch_pins(package: Path, srcinfo: Srcinfo, repository: str) -> list[tuple[str, str]]:
    """The head of each branch _commit_BRANCH pins (the branches of _sdks), and pkgver from the date of
    the newest commit, or with only older commits the next pkgrel."""
    pkgbuild = (package / "PKGBUILD").read_text()
    remote = subprocess.run(
        ["git", "ls-remote", "--heads", f"https://github.com/{repository}.git"],
        capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    heads = {
        ref.removeprefix("refs/heads/"): head
        for head, ref in (line.split("\t") for line in remote.splitlines())
    }
    version, pkgver, changed = srcinfo.first("pkgver"), srcinfo.first("pkgver"), False
    pins = []
    for branch in array(pkgbuild, "_sdks"):
        head = heads.get(branch, "")
        pins.append((f"_commit_{branch}", head))
        if not head or head == pin_value(package / "PKGBUILD", f"_commit_{branch}"):
            continue
        changed = True
        commit = request_json(f"https://api.github.com/repos/{repository}/commits/{head}")
        date = (
            str(commit.get("commit", {}).get("committer", {}).get("date", ""))
            if isinstance(commit, dict)
            else ""
        )
        date = date[:10].replace("-", "")
        if re.fullmatch(r"[0-9]{8}", date) and int(date) > int(version):
            version = date
    pins.append(("pkgver", version))
    if changed and version == pkgver:
        pins.append(("pkgrel", str(int(srcinfo.first("pkgrel")) + 1)))
    return pins


def settings(checkout: Checkout) -> dict[str, Any]:
    """pins.toml: the packages whose pins need more than the lookups by their pkgver."""
    return tomllib.loads((checkout.root / "pins.toml").read_text())


def resolve_pins(checkout: Checkout, name: str) -> list[tuple[str, str]]:
    """The values a package's pins should have, empty where they can't be determined; none without pins.

    As pins.toml says for the package, else the _commit a pkgver like git describe's names, else the
    commit of the NuGet package of the version.
    """
    package = checkout.root / name
    srcinfo = Srcinfo.load(package)
    version = srcinfo.first("pkgver")
    setting = settings(checkout).get(package.name, {})
    if "branches" in setting:
        return branch_pins(package, srcinfo, setting["branches"])
    if "file" in setting:
        url = setting["file"]["url"].format(pkgver=version)
        return [(setting["file"]["pin"], file_value(url, setting["file"]["pattern"]))]
    if not re.fullmatch(r"[0-9a-f]{7,40}", pin_value(package / "PKGBUILD", "_commit")):
        return []
    if "vmr" in setting:
        return [("_commit", vmr_commit(version, setting["vmr"]))]
    if re.search(r"\.g[0-9a-f]{7,40}$", version):
        return [("_commit", described_commit(srcinfo, version))]
    return [("_commit", nuget_commit(package, (package / "PKGBUILD").read_text(), version))]


def update_checksums(package: Path) -> None:
    """updpkgsums on a package whose pins changed, without the .part files of interrupted downloads.

    makepkg resumes those with a range request, which GitHub's archives of a commit, made on the fly,
    don't support, so curl would fail on every later try until the file is gone.
    """
    for part in package.glob("*.part"):
        part.unlink()
    subprocess.run(["updpkgsums"], cwd=package, check=True)


def refresh(package: Path) -> None:
    """Format the PKGBUILD (updpkgsums aligns the checksums its own way) and regenerate .SRCINFO."""
    subprocess.run(["shfmt", "--write", "PKGBUILD"], cwd=package, check=True)
    srcinfo = subprocess.run(
        ["makepkg", "--printsrcinfo"], cwd=package, capture_output=True, text=True, check=True
    )
    (package / ".SRCINFO").write_text(srcinfo.stdout)


def run_online(checkout: Checkout, packages: Sequence[str], update: bool) -> int:
    """For each package that pins something, whether its pins are what its version names, online.

    The upstream commit its pkgver was published from, and what a PKGBUILD's _pins_lookup prints
    (submodule commits, branch heads, versions of other packages); with update, rewrite stale ones
    and refresh the checksums and .SRCINFO.
    """
    require(
        "pins --online",
        [("curl", "curl")] + ([("updpkgsums", "pacman-contrib"), ("shfmt", "shfmt")] if update else []),
    )
    for name in checkout.select(packages):
        package = checkout.root / name
        pins = resolve_pins(checkout, name)
        if not pins:
            continue
        changed = False
        good = 0
        for pin, new in pins:
            current = pin_value(package / "PKGBUILD", pin)
            if not new:
                print(f"{name:<38} {pin} unresolved (current {short_pin(current)})")
            elif new == current:
                good += 1
            elif update:
                set_pin(package / "PKGBUILD", pin, new)
                changed = True
                print(f"{name:<38} {pin} updated {short_pin(current)} -> {short_pin(new)}")
            else:
                print(f"{name:<38} {pin} STALE {short_pin(current)} -> {short_pin(new)}")
        if good == len(pins):
            if good == 1:
                print(f"{name:<38} ok {pins[0][0]} {short_pin(pins[0][1])}")
            else:
                print(f"{name:<38} ok, {good} pins")
        if changed:
            update_checksums(package)
            refresh(package)
    return 0


def run_pins(checkout: Checkout, packages: Sequence[str]) -> int:
    """That a _commit is the commit a pkgver like git describe's (….r83.g4b8b3d3) names, offline."""
    status = 0
    for package in checkout.select([name.removesuffix("/PKGBUILD") for name in packages]):
        pkgbuild = checkout.root / package / "PKGBUILD"
        pkgver, commit = pin_value(pkgbuild, "pkgver"), pin_value(pkgbuild, "_commit")
        match = re.search(r"\.g([0-9a-f]{7,40})$", pkgver)
        if match and commit and not commit.startswith(match[1]):
            print(
                f"{package}/PKGBUILD: _commit {short_pin(commit)} isn't the commit pkgver names, "
                f"{match[1]}: ./aur-packages pins --update {package}"
            )
            status = 1
    return status


def run_upgrade(checkout: Checkout, packages: Sequence[str]) -> int:
    """Upgrade packages to their latest upstream version (pkgctl version upgrade), with their pins.

    pkgctl bumps pkgver but leaves the pins at the old release, so they move to the new version's
    before the checksums are taken, so that the sources and sums match the new version. Fails if a
    pin couldn't be moved, as the package would build the old sources under the new version.
    """
    require(
        "upgrade",
        [
            ("pkgctl", "devtools"),
            ("nvchecker", "nvchecker"),
            ("updpkgsums", "pacman-contrib"),
            ("shfmt", "shfmt"),
            ("curl", "curl"),
        ],
    )
    from aur_packages.updates import checked_packages

    checked = checked_packages(checkout, packages)
    if not checked:
        return 0
    subprocess.run(["pkgctl", "version", "upgrade", *checked], check=False)
    changed = paths("diff", "--name-only", "--", *(f"{p}/PKGBUILD" for p in checked))
    unresolved = []
    for path in changed:
        name = path.removesuffix("/PKGBUILD")
        package = checkout.root / name
        pins = resolve_pins(checkout, name)
        for pin, new in pins:
            current = pin_value(package / "PKGBUILD", pin)
            if not new:
                print(
                    f"  couldn't resolve {pin} of {name}'s new version, left at {short_pin(current)}",
                    file=sys.stderr,
                )
                unresolved.append(f"{name} {pin}")
            elif new != current:
                set_pin(package / "PKGBUILD", pin, new)
                print(f"  {pin} {short_pin(current)} -> {short_pin(new)}")
        if pins:
            update_checksums(package)
        refresh(package)
        print(f"Upgraded {name}")
    if unresolved:
        print(
            "Pins left at the old version, e.g. after GitHub's rate limit; run ./aur-packages pins --update "
            "on the packages later, or set them by hand:",
            file=sys.stderr,
        )
        for entry in unresolved:
            print(f"  {entry}", file=sys.stderr)
        return 1
    return 0
