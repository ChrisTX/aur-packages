"""The daily update check and its tray icon: tray install, remove and run."""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from aur_packages import state
from aur_packages.repo import Checkout
from aur_packages.updates import RETRY_UNIT

SERVICE = "aur-packages-updates.service"
TIMER = "aur-packages-updates.timer"
# The application ID of the tray icon, its name on the session bus
APP_ID = "info.rev_crew.AurPackagesTray"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def systemctl(*arguments: str, check: bool = True) -> None:
    subprocess.run(["systemctl", "--user", *arguments], check=check, capture_output=not check)


def unit_value(value: str) -> str:
    """A value for a quoted unit setting: systemd unquotes it and expands specifiers (%)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")


def exec_argument(value: str) -> str:
    """An argument of a desktop entry's Exec key, quoted, then escaped once more as a string value."""
    quoted = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return '"' + quoted.replace("\\", "\\\\") + '"'


def run_install(checkout: Checkout) -> int:
    """Install the daily update check of this checkout's packages and the tray icon's autostart."""
    root = checkout.root
    if importlib.util.find_spec("gi") is None:
        print("The tray icon needs python-gobject, the check is installed anyway", file=sys.stderr)
    if shutil.which("wl-copy") is None:
        print("Copying the upgrade command needs wl-clipboard", file=sys.stderr)
    units = config_home() / "systemd" / "user"
    # --force replaces the links of another checkout
    systemctl("link", "--force", str(root / "systemd" / SERVICE), str(root / "systemd" / TIMER))
    dropin = units / f"{SERVICE}.d" / "checkout.conf"
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text(
        "# Installed by ./aur-packages tray install: the checkout whose packages are checked\n"
        f'[Service]\nEnvironment="AUR_PACKAGES_HOME={unit_value(str(root))}"\n'
    )
    systemctl("daemon-reload")
    systemctl("enable", "--now", TIMER)
    autostart = config_home() / "autostart" / "aur-packages-tray.desktop"
    autostart.parent.mkdir(parents=True, exist_ok=True)
    autostart.write_text(
        "[Desktop Entry]\nType=Application\nName=AUR package updates\n"
        "Comment=Tray icon of the update check of the AUR packages, installed by ./aur-packages tray install\n"
        "Icon=system-software-update\n"
        f"Exec={exec_argument(str(root / 'aur-packages'))} tray run\n"
        "NoDisplay=true\nX-GNOME-Autostart-enabled=true\n"
    )
    print(f"Installed the units of {root / 'systemd'}, {dropin} and {autostart}")
    # A first result for the tray, and the tray itself in a graphical session
    systemctl("start", "--no-block", SERVICE)
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        subprocess.Popen(
            [str(root / "aur-packages"), "tray", "run"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print("Started the tray icon")
    return 0


def run_remove(checkout: Checkout) -> int:
    """Remove the update check and the tray icon again; the last result stays."""
    units = config_home() / "systemd" / "user"
    systemctl("disable", "--now", TIMER, check=False)
    systemctl("stop", SERVICE, f"{RETRY_UNIT}-*.timer", check=False)
    # disable removes the links of systemctl link as well, these are what might be left
    for leftover in (units / SERVICE, units / TIMER):
        leftover.unlink(missing_ok=True)
    shutil.rmtree(units / f"{SERVICE}.d", ignore_errors=True)
    systemctl("daemon-reload")
    (config_home() / "autostart" / "aur-packages-tray.desktop").unlink(missing_ok=True)
    # The tray quits by its action, if it's running
    path = "/" + APP_ID.replace(".", "/")
    subprocess.run(
        ["gdbus", "call", "--session", "--dest", APP_ID, "--object-path", path,
         "--method", "org.freedesktop.Application.ActivateAction", "quit", "[]", "{}"],
        capture_output=True,
        check=False,
    )  # fmt: skip
    print(f"Removed the update check and the tray icon; the last result stays in {state.state_file().parent}")
    return 0


def run_icon(checkout: Checkout) -> int:
    """Show the tray icon, which needs python-gobject, until it quits."""
    if importlib.util.find_spec("gi") is None:
        print("The tray icon needs python-gobject", file=sys.stderr)
        return 1
    from aur_packages import tray_icon

    return tray_icon.run()
