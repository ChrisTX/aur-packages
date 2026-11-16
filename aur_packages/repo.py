"""The checkout and its packages: the AUR's at the top level, local/ and overrides/."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Templates of build, expanded to their root packages
BUILD_TEMPLATES: dict[str, tuple[str, ...]] = {
    "powershell-core": ("powershell",),
    "powershell-full": (
        "powershell",
        "powershell-editor-services",
        "powershell-dsc",
        "vscode-powershell",
        "powershell-mmi",
        "powershell-pester-4",
        "powershell-powershellget-v3",
    ),
}

# The folders of packages that aren't published to the AUR
OUTSIDE_AUR = ("local", "overrides")


class SelectionError(Exception):
    """A package argument that isn't a package, or not one the command takes."""


@dataclass(frozen=True)
class Checkout:
    """A checkout of this repository, and the directory a command was called from."""

    root: Path
    cwd: Path

    def package_dirs(self) -> list[str]:
        """The folders of all packages, relative to the root: the top level, local/, overrides/."""
        dirs = sorted(p.parent.name for p in self.root.glob("*/PKGBUILD"))
        for outside in OUTSIDE_AUR:
            dirs += sorted(f"{outside}/{p.parent.name}" for p in self.root.glob(f"{outside}/*/PKGBUILD"))
        return dirs

    def package_dir(self, name: str) -> str | None:
        """The folder of a package given by folder or name, None if it isn't one."""
        name = name.rstrip("/")
        for candidate in (name, *(f"{outside}/{name}" for outside in OUTSIDE_AUR)):
            if (self.root / candidate / "PKGBUILD").is_file():
                return candidate
        return None

    def select(self, names: Iterable[str], *, aur_only: bool = False) -> list[str]:
        """The folders of the packages given, or of all of them (with aur_only, the AUR's)."""
        names = list(names)
        if not names:
            dirs = self.package_dirs()
            return [d for d in dirs if "/" not in d] if aur_only else dirs
        selected = []
        for name in names:
            folder = self.package_dir(name)
            if folder is None:
                raise SelectionError(f"Not a package: {name}")
            if aur_only and "/" in folder:
                raise SelectionError(
                    f"Not an AUR package: {folder} (local/ and overrides/ aren't published to the AUR)"
                )
            selected.append(folder)
        return selected
