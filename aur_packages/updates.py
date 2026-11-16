"""The update check: updates (pkgctl version check), and with --state the state file of the tray."""

import json
import os
import re
import subprocess
import sys
import time
import tomllib
import urllib.request
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from aur_packages import maintainers, state
from aur_packages.repo import Checkout
from aur_packages.tools import require

# The transient units of the retries after a rate limit, aur-packages-updates-retry-<time>.timer
RETRY_UNIT = "aur-packages-updates-retry"


def checked_packages(checkout: Checkout, packages: Sequence[str]) -> list[str]:
    """The selected packages with an update check (.nvchecker.toml); VCS packages have none."""
    return [p for p in checkout.select(packages) if (checkout.root / p / ".nvchecker.toml").exists()]


def github_token() -> str:
    """The GitHub token of nvchecker's keyfile, else the one gh is logged in with, empty without."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    keyfile = config / "nvchecker" / "keyfile.toml"
    if keyfile.exists():
        try:
            token = tomllib.loads(keyfile.read_text()).get("keys", {}).get("github", "")
            if isinstance(token, str) and token:
                return token
        except tomllib.TOMLDecodeError:
            pass
    try:
        result = subprocess.run(
            ["gh", "auth", "token", "--hostname", "github.com"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def rate_limit_reset() -> int:
    """When GitHub's rate limit resets, the latest exhausted one's, else now (the limit has room).

    From its rate_limit endpoint, which doesn't count against the limit, with github_token's token.
    """
    request = urllib.request.Request("https://api.github.com/rate_limit")
    if token := github_token():
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        resources = json.load(response).get("resources", {})
    resets = [r["reset"] for r in resources.values() if r.get("remaining") == 0]
    return int(max(resets, default=time.time()))


def rate_limited(message: str) -> bool:
    """A 403 or 429 of GitHub's API, or nvchecker saying so."""
    if re.search("rate limit", message, re.IGNORECASE):
        return True
    return "api.github.com" in message and bool(re.search(r"(HTTPError\(|HTTP )(403|429)", message))


def short(message: str) -> str:
    """tornado's HTTPError, which shows its whole response: its code, reason and URL."""
    if error := re.search(r"HTTPError\((?P<code>[0-9]+), '(?P<reason>[^']*)'", message):
        url = re.search(r"effective_url='(?P<url>[^']*)'", message)
        return f"HTTP {error['code']} {error['reason']}" + (f" ({url['url']})" if url else "")
    return message.split("\n", 1)[0].removeprefix("unexpected error happened: ")


def check(packages: Sequence[str]) -> dict[str, Any]:
    """What pkgctl version check finds: the outdated packages, failures, rate limits, an error."""
    result = subprocess.run(
        ["pkgctl", "version", "check", "--json", *packages], capture_output=True, text=True, check=False
    )
    try:
        results = json.loads(result.stdout) if result.returncode == 0 else None
    except json.JSONDecodeError:
        results = None
    if not isinstance(results, list):
        last = (result.stderr.strip().splitlines() or [""])[-1]
        return {"error": f"pkgctl version check failed: {last}"}
    failed = [r for r in results if r.get("status") == "failure"]
    messages = {r["pkgbase"]: r.get("message") or "" for r in failed}
    every_failed = packages and len(failed) == len(packages)
    return {
        "results": True,
        "updates": [
            {"package": r["pkgbase"], "current": r["local_version"], "new": r["upstream_version"]}
            for r in results
            if r.get("status") == "success" and r.get("out_of_date")
        ],
        "failed": [r["pkgbase"] for r in failed],
        "failures": [
            {"package": name, "message": short(message or "failed")}
            for name, message in messages.items()
            if not rate_limited(message)
        ],
        "rate_limited": [name for name, message in messages.items() if rate_limited(message)],
        # Not when only the rate limit stopped them: they wait for the retry
        "error": "No package could be checked, e.g. without a network connection"
        if every_failed and any(not rate_limited(m) for m in messages.values())
        else None,
    }


def merge(new: dict[str, Any], previous: dict[str, Any], names: list[str], checkout: Path) -> dict[str, Any]:
    """The new state: this check's findings, and the earlier ones of the packages it didn't learn about.

    Packages that weren't checked, or whose check failed, keep their entries, so a rate limit or a
    missing network doesn't make updates disappear. By name (pkgbase), as pkgctl reports them.
    """
    known = [n for n in names if n not in new.get("failed", [])] if new.get("results") else []
    tried = names if new.get("results") else []
    waiting = (previous.get("rate_limited") or {}).get("packages") or []
    return {
        "checked": datetime.now().astimezone().isoformat(timespec="seconds"),
        "checkout": str(checkout),
        "error": new.get("error"),
        "updates": sorted(
            new.get("updates", []) + [u for u in previous.get("updates") or [] if u["package"] not in known],
            key=lambda u: str(u["package"]),
        ),
        "failures": sorted(
            new.get("failures", [])
            + [f for f in previous.get("failures") or [] if f["package"] not in tried],
            key=lambda f: str(f["package"]),
        ),
        "rate_limited": {
            "packages": sorted(set(new.get("rate_limited", []) + [w for w in waiting if w not in tried])),
            "retry": None,
        },
    }


def schedule_retry(root: Path, packages: list[str], reset: int) -> None:
    """A transient timer that checks the rate-limited packages again a minute after the reset."""
    environment = ["--setenv=PATH"] + (
        ["--setenv=XDG_STATE_HOME"] if os.environ.get("XDG_STATE_HOME") else []
    )
    command = [
        "systemd-run", "--user", "--quiet", "--collect", f"--unit={RETRY_UNIT}-{reset}",
        f"--on-active={max(reset + 60 - int(time.time()), 1)}", "--timer-property=AccuracySec=1min",
        "--property=Type=oneshot", "--description=Check the AUR packages that hit GitHub's rate limit",
        *environment, "/usr/bin/python3", str(root / "aur-packages"), "updates", "--state", "--retry", *packages,
    ]  # fmt: skip
    if subprocess.run(command, check=False).returncode:
        print("Couldn't schedule checking the rate-limited packages again", file=sys.stderr)


def summary(current: dict[str, Any]) -> list[str]:
    lines = [f"{u['package']} {u['current']} -> {u['new']}" for u in current["updates"]]
    lines += [f"{f['package']}: check failed: {f['message']}" for f in current["failures"]]
    limited = current["rate_limited"]
    if limited["packages"]:
        lines.append(
            f"GitHub's rate limit, checked again at {limited['retry']}: {' '.join(limited['packages'])}"
        )
    lines += [f"{n['folder']}: {n['message']}" for n in current.get("maintainers", [])]
    lines += [f"{n['folder']}: {n['reference']} {n['message']}" for n in current.get("upstream", [])]
    if current["error"]:
        lines.append(f"Error: {current['error']}")
    return lines


def upstream_notes(checkout: Checkout, folder: Path, previous: dict[str, Any]) -> list[dict[str, str]]:
    """The notes on the upstream pull requests the packages refer to (see upstream.notes), with a
    GitHub token only: about a request per open pull request a day, which the 60 an hour without
    one don't leave room for. Those of the last check if a request failed."""
    from aur_packages import upstream

    if not github_token():
        return []
    try:
        found = upstream.notes(checkout, folder / "upstream-cache.json")
    except Exception:  # noqa: BLE001 (GitHub unreachable, whatever the error)
        found = None
    return found if found is not None else previous.get("upstream") or []


def run_state(checkout: Checkout, packages: Sequence[str], schedule: bool) -> int:
    """Check like updates, and write the result to the state file the tray shows.

    With schedule (the service of tray install), a transient timer checks the rate-limited packages
    again once the limit resets; a check by hand neither leaves timers behind nor cancels them. If no
    package could be checked, the state says so, and it fails. Written in one step under the lock.
    """
    checked = checked_packages(checkout, packages)
    path = state.state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with state.locked(path):
        try:
            previous = json.loads(path.read_text()) if path.exists() else {}
        except json.JSONDecodeError:
            previous = {}
        previous = previous if isinstance(previous, dict) else {}
        new = check(checked)
        current = merge(new, previous, [p.rsplit("/", 1)[-1] for p in checked], checkout.root)
        # The notes on the maintainers on the AUR, of all packages; without the AUR's answer, the old ones
        try:
            current["maintainers"] = maintainers.notes(
                [p for p in checkout.package_dirs() if not p.startswith("overrides/")]
            )
        except Exception:  # noqa: BLE001 (the AUR unreachable, whatever the error)
            current["maintainers"] = previous.get("maintainers") or []
        current["upstream"] = upstream_notes(checkout, path.parent, previous)
        # Only one retry is pending, the one for the packages that wait now
        if schedule:
            subprocess.run(
                ["systemctl", "--user", "stop", f"{RETRY_UNIT}-*.timer"], capture_output=True, check=False
            )
        retry = current["rate_limited"]["packages"]
        if retry:
            try:
                reset = rate_limit_reset()
            except OSError, ValueError:
                reset = int(time.time()) + 3600 - 60
            current["rate_limited"]["retry"] = (
                datetime.fromtimestamp(reset + 60).astimezone().isoformat(timespec="seconds")
            )
            if schedule:
                schedule_retry(checkout.root, retry, reset)
        state.write(path, current)
    for line in summary(current):
        print(line)
    return 1 if current["error"] else 0


def run_updates(checkout: Checkout, packages: Sequence[str], write_state: bool, retry: bool) -> int:
    """Show which packages have a newer upstream version, or with write_state, write the state file."""
    require("updates", [("pkgctl", "devtools"), ("nvchecker", "nvchecker")])
    if write_state:
        return run_state(checkout, packages, retry)
    checked = checked_packages(checkout, packages)
    if not checked:
        return 0
    return subprocess.run(["pkgctl", "version", "check", *checked], check=False).returncode
