"""The update check: updates, and with --state the state file of the tray.

The packages' .nvchecker.toml files are checked by one nvchecker run, which checks them in parallel
and asks for each URL once, instead of pkgctl version check, which runs nvchecker for one package
after the other: seconds instead of minutes. The results are pkgctl's: its rules for the files, its
git environment, and its comparison with the pkgver (versions); pkgctl version upgrade stays as it is.

pkgctl doing the same is proposed upstream: archlinux/devtools!354 (issue #279), opened 2026-11-17,
85 packages in about 6 s instead of 56 s, with the same output. Until a devtools release has it,
this module replicates pkgctl's rules; once one does, updates can call pkgctl version check again
and drop config_problem, nvchecker and the comparison, which is what that merge request does.
https://gitlab.archlinux.org/archlinux/devtools/-/merge_requests/354
"""

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
from aur_packages.overrides import vercmp
from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import require

# The transient units of the retries after a rate limit, aur-packages-updates-retry-<time>.timer
RETRY_UNIT = "aur-packages-updates-retry"


def checked_packages(checkout: Checkout, packages: Sequence[str]) -> list[str]:
    """The selected packages with an update check (.nvchecker.toml); VCS packages have none."""
    return [p for p in checkout.select(packages) if (checkout.root / p / ".nvchecker.toml").exists()]


# Properties pkgctl refuses in a .nvchecker.toml: secrets belong into the keyfile
RESTRICTED = ("keyfile", "httptoken", "token")

# pkgctl version check's exit statuses
EXIT_OUT_OF_DATE = 2
EXIT_FAILURE = 3


def config_problem(config: dict[str, Any], pkgbase: str) -> str:
    """Why pkgctl wouldn't check a package's .nvchecker.toml, empty if it would: only its pkgbase's
    entry (and pkgbase:… ones), no secrets, and not the cmd source, which runs commands."""
    for name, entry in config.items():
        if name != pkgbase and not name.startswith(f"{pkgbase}:"):
            return f"non-pkgbase section not supported in .nvchecker.toml: [{name}]"
        if not isinstance(entry, dict):
            return f"not a section in .nvchecker.toml: {name}"
        if restricted := [key for key in RESTRICTED if key in entry]:
            return f"restricted property in .nvchecker.toml: {restricted[0]}"
        if entry.get("source") == "cmd":
            return "using the 'cmd' source in .nvchecker.toml is disallowed"
    if pkgbase not in config:
        return f"missing pkgbase section in .nvchecker.toml: {pkgbase}"
    return ""


def keyfile() -> Path:
    """nvchecker's keyfile, which pkgctl passes to it, with the GitHub token."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "nvchecker" / "keyfile.toml"


def nvchecker(files: Sequence[str]) -> tuple[dict[str, str], dict[str, str], str]:
    """The upstream versions of the entries, and the errors of those without, from one nvchecker
    run over the .nvchecker.toml files joined, which config_problem has checked: each has only its
    pkgbase's sections, so they don't clash. And nvchecker's own error, empty unless it failed as a
    whole."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="aur-packages-nvchecker.") as folder:
        file = Path(folder) / "nvchecker.toml"
        file.write_text("\n".join(files))
        # As pkgctl: git without the user's configuration, and never asking for credentials
        environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_GLOBAL": "/dev/null"}
        environment["GIT_CONFIG_SYSTEM"] = "/dev/null"
        key = ["--keyfile", str(keyfile())] if keyfile().exists() else []
        result = subprocess.run(
            ["nvchecker", "--file", str(file), "--logger", "json", *key],
            capture_output=True, text=True, env=environment, check=False,
        )  # fmt: skip
    found: dict[str, str] = {}
    errors: dict[str, list[str]] = {}
    for line in (result.stdout + result.stderr).splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or "name" not in event:
            continue
        if event.get("event") == "updated":
            found[event["name"]] = str(event.get("version"))
        # As pkgctl's: the errors with a message, each as event: error
        elif event.get("level") == "error" and event.get("error") is not None:
            errors.setdefault(event["name"], []).append(f"{event.get('event')}: {event['error']}")
    failure = ""
    if result.returncode and not found and not errors:
        failure = (result.stderr.strip().splitlines() or [f"exit status {result.returncode}"])[-1]
    return found, {name: "\n".join(lines) for name, lines in errors.items()}, failure


def versions(checkout: Checkout, packages: Sequence[str]) -> list[dict[str, Any]] | str:
    """pkgctl version check --json --verbose of the packages: for each, its pkgbase, status (success,
    failure), message, out_of_date, local_version (pkgver) and upstream_version; or why nvchecker
    failed as a whole."""
    results: dict[str, dict[str, Any]] = {}
    configs: dict[str, dict[str, Any]] = {}
    files: list[str] = []
    pkgvers: dict[str, str] = {}
    for package in packages:
        srcinfo = Srcinfo.load(checkout.root / package)
        pkgbase, pkgver = srcinfo.pkgbase, srcinfo.first("pkgver")
        pkgvers[pkgbase] = pkgver
        text = (checkout.root / package / ".nvchecker.toml").read_text()
        try:
            config = tomllib.loads(text)
        except tomllib.TOMLDecodeError as error:
            problem = f"invalid .nvchecker.toml: {error}"
        else:
            problem = config_problem(config, pkgbase)
        if problem:
            results[pkgbase] = failure(pkgbase, problem, pkgver)
        else:
            configs[pkgbase] = config
            files.append(text)
    found, errors, failed = nvchecker(files) if files else ({}, {}, "")
    if failed:
        return failed
    for pkgbase, config in configs.items():
        pkgver, upstream = pkgvers[pkgbase], found.get(pkgbase)
        if pkgbase in errors:
            results[pkgbase] = failure(pkgbase, errors[pkgbase], pkgver)
            continue
        if upstream is None:
            results[pkgbase] = failure(pkgbase, "failed to select pkgbase result from output", pkgver)
            continue
        # As pkgctl: the manual source of meta packages is always up to date
        if upstream == "None" and config[pkgbase].get("source") == "manual":
            upstream = pkgver
        try:
            newer = vercmp(upstream, pkgver)
        except subprocess.CalledProcessError, ValueError:
            message = f"failed to compare version {upstream} against {pkgver}"
            results[pkgbase] = failure(pkgbase, message, pkgver, upstream)
            continue
        results[pkgbase] = {
            "pkgbase": pkgbase,
            "status": "success" if newer >= 0 else "warning",
            "message": None if newer >= 0 else "local version is newer than upstream",
            "out_of_date": newer > 0,
            "local_version": pkgver,
            "upstream_version": upstream,
        }
    return [results[pkgbase] for pkgbase in pkgvers]


def failure(pkgbase: str, message: str, pkgver: str, upstream: str | None = None) -> dict[str, Any]:
    return {
        "pkgbase": pkgbase,
        "status": "failure",
        "message": message,
        "out_of_date": False,
        "local_version": pkgver or None,
        "upstream_version": upstream,
    }


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


def check(checkout: Checkout, packages: Sequence[str]) -> dict[str, Any]:
    """What the check finds: the outdated packages, failures, rate limits, an error."""
    results = versions(checkout, packages)
    if isinstance(results, str):
        return {"error": f"nvchecker failed: {results}"}
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
    missing network doesn't make updates disappear. By name (pkgbase), as versions reports them.
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
        new = check(checkout, checked)
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
    require("updates", [("nvchecker", "nvchecker"), ("vercmp", "pacman")])
    if write_state:
        return run_state(checkout, packages, retry)
    checked = checked_packages(checkout, packages)
    if not checked:
        return 0
    results = versions(checkout, checked)
    if isinstance(results, str):
        print(f"nvchecker failed: {results}", file=sys.stderr)
        return EXIT_FAILURE
    for line in report(results):
        print(line)
    # As pkgctl version check: failures, else outdated packages
    if any(r["status"] == "failure" for r in results):
        return EXIT_FAILURE
    return EXIT_OUT_OF_DATE if any(r["out_of_date"] for r in results) else 0


def report(results: list[dict[str, Any]]) -> list[str]:
    """pkgctl version check's sections, without its colours: failures, outdated packages, summary."""
    failed = [r for r in results if r["status"] == "failure"]
    outdated = [r for r in results if r["out_of_date"]]
    lines = []
    if failed:
        lines += ["Failure"] + [f"  {r['pkgbase']}: {short(r['message'])}" for r in failed]
    if outdated:
        lines += ["Out-of-date"] + [
            f"  {r['pkgbase']}: upgrade from version {r['local_version']} to {r['upstream_version']}"
            for r in outdated
        ]
    current = len(results) - len(failed) - len(outdated)
    counts = [("Up-to-date", current), ("Failure", len(failed)), ("Out-of-date", len(outdated))]
    lines.append("Summary: " + ", ".join(f"{name} {count}" for name, count in counts if count))
    return lines
