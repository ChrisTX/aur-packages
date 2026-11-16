"""The pins of the PKGBUILDs: commits and other values a version names, offline and online.

pins (offline, the hook) checks that a _commit is the commit a pkgver like git describe's names;
pins --online looks up what every pin should be, and --update rewrites the stale ones.
"""

import os
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from aur_packages.repo import Checkout
from aur_packages.tools import require
from aur_packages.updates import github_token

# The lookups run in bash, as they source the PKGBUILD and may call its _pins_lookup or _commit_lookup.
# Their requests give up on a stalled connection and try again, instead of waiting forever; those to
# GitHub's API go with the token ($PINS_GITHUB_TOKEN, on curl's stdin rather than its command line,
# where other users could read it), so they get its rate limit rather than the 60 requests an hour
# without one. Prints "NAME VALUE" a line, the value empty if it can't be determined.
LOOKUP = r"""
curl() {
  local arg
  local -a stall=(--connect-timeout 15 --speed-limit 1024 --speed-time 30 --retry 2)
  if [[ -n "${PINS_GITHUB_TOKEN:-}" ]]; then
    for arg; do
      if [[ "$arg" == https://api.github.com/* ]]; then
        command curl "${stall[@]}" -K - "$@" <<<"header = \"Authorization: Bearer $PINS_GITHUB_TOKEN\""
        return
      fi
    done
  fi
  command curl "${stall[@]}" "$@"
}
# The upstream commit the current pkgver was published from, best effort: the <repository commit> of
# the published NuGet nuspec, by the package's NuGet id (_nugetid, else the first of _packages, else
# the .nvchecker.toml's packageid), unless the PKGBUILD has a _commit_lookup
resolve_commit() {
  local id ver lid base out tmp
  if declare -F _commit_lookup >/dev/null; then
    _commit_lookup
    return
  fi
  id=${_nugetid:-}
  if [[ -z "$id" && -n "${_packages+x}" && ${#_packages[@]} -gt 0 ]]; then id=${_packages[0]}; fi
  if [[ -z "$id" && -f .nvchecker.toml ]]; then
    id=$(sed -n -E 's/.*packageid:([^&"]+).*/\1/p' .nvchecker.toml | head -1)
  fi
  [[ -n "$id" ]] || return 1
  ver=$pkgver
  lid=${id,,}
  base="https://api.nuget.org/v3-flatcontainer/$lid/$ver"
  # The flat container serves the nuspec on its own; else from the whole package
  out=$(curl -fsSL "$base/$lid.nuspec" 2>/dev/null) || out=''
  if [[ -z "$out" ]]; then
    tmp=$(mktemp) || return 1
    if curl -fsSL "$base/$lid.$ver.nupkg" -o "$tmp" 2>/dev/null; then
      out=$(bsdtar -xOf "$tmp" '*.nuspec' 2>/dev/null)
    fi
    rm -f "$tmp"
  fi
  printf '%s' "$out" | grep -oiE 'commit="[0-9a-f]{40}"' | grep -oiE '[0-9a-f]{40}' | head -1
}
source ./PKGBUILD >/dev/null 2>&1 || exit 1
if declare -F _pins_lookup >/dev/null; then
  _pins_lookup
  exit
fi
[[ "${_commit-}" =~ ^[0-9a-f]{7,40}$ ]] || exit 0
echo "_commit $(resolve_commit)"
"""


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


def resolve_pins(package: Path) -> list[tuple[str, str]]:
    """The values a package's pins should have, by the lookups of LOOKUP; none without pins."""
    env = {**os.environ, "PINS_GITHUB_TOKEN": github_token()}
    result = subprocess.run(
        ["bash", "-c", LOOKUP], cwd=package, capture_output=True, text=True, env=env, check=False
    )
    pins = []
    for line in result.stdout.splitlines():
        name, _, value = line.partition(" ")
        if name:
            pins.append((name, "" if value.strip() == "null" else value.strip()))
    return pins


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
        pins = resolve_pins(package)
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
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--", *(f"{p}/PKGBUILD" for p in checked)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    unresolved = []
    for path in changed:
        name = path.removesuffix("/PKGBUILD")
        package = checkout.root / name
        pins = resolve_pins(package)
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
