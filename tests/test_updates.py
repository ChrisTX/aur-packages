"""The update check's state, which the tray shows, and the tray's installed files."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aur_packages import tray, updates
from aur_packages.repo import Checkout


def test_rate_limited() -> None:
    assert updates.rate_limited("API rate limit exceeded")
    assert updates.rate_limited("HTTPError(403, 'Forbidden') https://api.github.com/repos/x")
    assert not updates.rate_limited("HTTPError(404, 'Not Found') https://api.github.com/repos/x")
    assert not updates.rate_limited("HTTPError(403, 'Forbidden') https://example.org")


def test_short() -> None:
    message = "HTTPError(404, 'Not Found', HTTPResponse(effective_url='https://x/y', code=404, …)) and more"
    assert updates.short(message) == "HTTP 404 Not Found (https://x/y)"
    assert updates.short("unexpected error happened: boom\ntraceback") == "boom"


def test_merge_keeps_what_this_check_didnt_learn() -> None:
    previous = {
        "updates": [
            {"package": "kept", "current": "1", "new": "2"},
            {"package": "fixed", "current": "1", "new": "2"},
        ],
        "failures": [{"package": "kept", "message": "old"}, {"package": "fixed", "message": "old"}],
        "rate_limited": {"packages": ["waiting", "fixed"], "retry": "later"},
    }
    new = {
        "results": True,
        "updates": [{"package": "new", "current": "1", "new": "3"}],
        "failed": ["broken"],
        "failures": [{"package": "broken", "message": "HTTP 500"}],
        "rate_limited": [],
        "error": None,
    }
    # fixed and new were checked; kept and waiting weren't, broken failed
    state = updates.merge(new, previous, ["fixed", "new", "broken"], Path("/checkout"))
    assert [u["package"] for u in state["updates"]] == ["kept", "new"]
    assert [f["package"] for f in state["failures"]] == ["broken", "kept"]
    assert state["rate_limited"] == {"packages": ["waiting"], "retry": None}
    assert state["checkout"] == "/checkout"


def test_merge_without_results_keeps_everything() -> None:
    previous = {
        "updates": [{"package": "a", "current": "1", "new": "2"}],
        "rate_limited": {"packages": ["b"]},
    }
    state = updates.merge({"error": "nvchecker failed: x"}, previous, ["a", "b"], Path("/c"))
    assert state["updates"] == previous["updates"]
    assert state["rate_limited"]["packages"] == ["b"]
    assert state["error"] == "nvchecker failed: x"


def test_summary() -> None:
    state = {
        "updates": [{"package": "a", "current": "1", "new": "2"}],
        "failures": [{"package": "b", "message": "HTTP 500"}],
        "rate_limited": {"packages": ["c"], "retry": "12:00"},
        "maintainers": [{"folder": "d", "message": "not on the AUR yet: push it"}],
        "error": None,
    }
    assert updates.summary(state) == [
        "a 1 -> 2",
        "b: check failed: HTTP 500",
        "GitHub's rate limit, checked again at 12:00: c",
        "d: not on the AUR yet: push it",
    ]


def test_quoting_of_the_installed_files() -> None:
    assert tray.unit_value('/home/a "b"/100%') == '/home/a \\"b\\"/100%%'
    assert tray.exec_argument("/home/a b/aur-packages") == '"/home/a b/aur-packages"'
    # quoted for the Exec key, then the backslashes once more for the string value
    assert tray.exec_argument('/x/$y"z') == '"/x/\\\\$y\\\\"z"'


def package(root: Path, pkgbase: str, pkgver: str, config: str) -> str:
    (root / pkgbase).mkdir()
    (root / pkgbase / ".SRCINFO").write_text(
        f"pkgbase = {pkgbase}\n\tpkgver = {pkgver}\n\tpkgrel = 1\n\npkgname = {pkgbase}\n"
    )
    (root / pkgbase / ".nvchecker.toml").write_text(config)
    return pkgbase


def test_config_problem() -> None:
    assert updates.config_problem({"a": {"source": "github"}, "a:extra": {}}, "a") == ""
    assert "non-pkgbase section" in updates.config_problem({"a": {}, "b": {}}, "a")
    assert "missing pkgbase section" in updates.config_problem({"a:extra": {}}, "a")
    assert "restricted property" in updates.config_problem({"a": {"token": "x"}}, "a")
    assert "'cmd' source" in updates.config_problem({"a": {"source": "cmd"}}, "a")


def test_versions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    names = [
        package(tmp_path, "current", "1.0", '[current]\nsource = "x"\n'),
        package(tmp_path, "outdated", "1.0", '[outdated]\nsource = "x"\n'),
        package(tmp_path, "newer", "2.0", '[newer]\nsource = "x"\n'),
        package(tmp_path, "meta", "1.0", '[meta]\nsource = "manual"\n'),
        package(tmp_path, "broken", "1.0", '[broken]\nsource = "x"\n'),
        package(tmp_path, "silent", "1.0", '[silent]\nsource = "x"\n'),
        package(tmp_path, "unsafe", "1.0", '[unsafe]\nsource = "cmd"\n'),
        package(tmp_path, "invalid", "1.0", "[invalid\n"),
    ]
    joined: list[str] = []

    def nvchecker(files: list[str]) -> tuple[dict[str, str], dict[str, str], str]:
        joined.extend(files)
        found = {"current": "1.0", "outdated": "1.1", "newer": "1.5", "meta": "None"}
        return found, {"broken": "unexpected error happened: HTTPError(500)"}, ""

    monkeypatch.setattr(updates, "nvchecker", nvchecker)
    found = updates.versions(Checkout(tmp_path, tmp_path), names)
    assert isinstance(found, list)
    results = {r["pkgbase"]: r for r in found}
    # Only the files pkgctl would check are passed on
    assert len(joined) == 6
    assert list(results) == names
    assert (results["current"]["status"], results["current"]["out_of_date"]) == ("success", False)
    assert results["outdated"]["out_of_date"] and results["outdated"]["upstream_version"] == "1.1"
    assert results["newer"]["status"] == "warning"
    assert results["meta"]["upstream_version"] == "1.0"
    assert results["broken"]["message"] == "unexpected error happened: HTTPError(500)"
    assert results["silent"]["message"] == "failed to select pkgbase result from output"
    assert "'cmd' source" in results["unsafe"]["message"]
    assert results["invalid"]["message"].startswith("invalid .nvchecker.toml")
    assert updates.report(list(results.values()))[-1] == "Summary: Up-to-date 3, Failure 4, Out-of-date 1"


def test_nvchecker_events(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [
        {"name": "a", "event": "updated", "version": "1.2", "level": "info"},
        {"name": "b", "event": "no source specified", "level": "error"},
        {
            "name": "b",
            "event": "no-result",
            "error": "GetVersionError('no source specified')",
            "level": "error",
        },
        {"name": "c", "event": "ignoring invalid version", "level": "warning"},
    ]
    output = "\n".join(json.dumps(line) for line in lines)

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
        return subprocess.CompletedProcess(command, 0, "", output)

    monkeypatch.setattr(subprocess, "run", run)
    found, errors, failure = updates.nvchecker(["[a]\n"])
    assert found == {"a": "1.2"}
    assert errors == {"b": "no-result: GetVersionError('no source specified')"}
    assert failure == ""
