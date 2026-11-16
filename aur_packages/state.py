"""The state file of the daily update check, which the tray icon shows."""

import fcntl
import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def state_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "aur-packages" / "updates.json"


@contextmanager
def locked(path: Path) -> Iterator[None]:
    """The lock of the state file, which updates --state holds while it writes it."""
    with (path.parent / ".updates.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def write(path: Path, state: object) -> None:
    """Replace the state file in one step, so the tray never reads half of it."""
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".updates.json.", delete=False) as file:
        file.write(json.dumps(state, indent=2) + "\n")
    os.replace(file.name, path)


def forget_pushed(package: str, version: str) -> None:
    """Drop a pushed package from the outdated ones once the version pushed is at least the new one.

    So the tray doesn't list it until the next check. A missing state file (no tray install) stays so.
    """
    path = state_file()
    if not path.exists():
        return
    with locked(path):
        try:
            state = json.loads(path.read_text())
        except json.JSONDecodeError:
            return
        updates = state.get("updates") or []
        new = next((u.get("new") for u in updates if u.get("package") == package), None)
        if not new:
            return
        newer = subprocess.run(["vercmp", new, version], capture_output=True, text=True, check=True).stdout
        if int(newer) > 0:
            return
        state["updates"] = [u for u in updates if u.get("package") != package]
        write(path, state)
    print(f"Removed {package} {new} from the update list of the tray")
