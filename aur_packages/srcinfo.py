"""The .SRCINFO of a package: its pkgbase section, and its packages."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Srcinfo:
    """The fields of the pkgbase section, and those of each package, in their order."""

    pkgbase: str = ""
    base: dict[str, list[str]] = field(default_factory=dict)
    packages: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> Srcinfo:
        srcinfo = cls()
        section = srcinfo.base
        for line in text.splitlines():
            key, separator, value = line.strip().partition(" = ")
            if not separator:
                continue
            if not line.startswith("\t") and key == "pkgbase":
                srcinfo.pkgbase = value
            elif not line.startswith("\t") and key == "pkgname":
                section = srcinfo.packages.setdefault(value, {})
            else:
                section.setdefault(key, []).append(value)
        return srcinfo

    @classmethod
    def load(cls, package: Path) -> Srcinfo:
        return cls.parse((package / ".SRCINFO").read_text())

    def first(self, key: str) -> str:
        """A field of the pkgbase section, empty if it has none."""
        return (self.base.get(key) or [""])[0]

    def version(self) -> str:
        """The full version, [epoch:]pkgver-pkgrel."""
        epoch = self.first("epoch")
        return f"{epoch + ':' if epoch else ''}{self.first('pkgver')}-{self.first('pkgrel')}"

    def pkgdesc(self) -> str:
        """The pkgdesc of the pkgbase, or without one, that of the package named like it."""
        if desc := self.first("pkgdesc"):
            return desc
        return (self.packages.get(self.pkgbase, {}).get("pkgdesc") or [""])[0]

    def pkgnames(self) -> list[str]:
        """The packages, the one named like the pkgbase first; without debug packages."""
        names = [name for name in self.packages if not name.endswith("-debug")]
        return sorted(names, key=lambda name: name != self.pkgbase)
