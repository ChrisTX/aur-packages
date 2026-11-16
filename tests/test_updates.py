"""The update check's state, which the tray shows, and the tray's installed files."""

from pathlib import Path

from aur_packages import tray, updates


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
    state = updates.merge({"error": "pkgctl version check failed: x"}, previous, ["a", "b"], Path("/c"))
    assert state["updates"] == previous["updates"]
    assert state["rate_limited"]["packages"] == ["b"]
    assert state["error"] == "pkgctl version check failed: x"


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
