"""The lookups of the pins: which one a package gets, and what they read from it."""

from pathlib import Path

import pytest

from aur_packages import pins
from aur_packages.repo import Checkout
from aur_packages.srcinfo import Srcinfo

COMMIT = "5b0aa725beef33c9cf6a1b00659a010c3d9120d3"


def package(root: Path, name: str, pkgver: str, pkgbuild: str) -> None:
    (root / name).mkdir()
    (root / name / "PKGBUILD").write_text(f"pkgver={pkgver}\n{pkgbuild}")
    (root / name / ".SRCINFO").write_text(
        f"pkgbase = {name}\n\tpkgver = {pkgver}\n\tpkgrel = 1\n"
        f"\tsource = {name}.tar.gz::https://github.com/owner/{name}/archive/{COMMIT}.tar.gz\n\npkgname = {name}\n"
    )


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Checkout:
    (tmp_path / "pins.toml").write_text(
        '[vmr]\nvmr = "runtime"\n\n[file]\nfile = { pin = "_sdk", url = "https://x/v{pkgver}", pattern = "a" }\n'
    )
    package(tmp_path, "described", "2.2.r84.g5b0aa72", f"_commit={COMMIT}\n")
    package(tmp_path, "nuget", "1.0.0", f"_nugetid=Some.Package\n_commit={COMMIT}\n")
    package(tmp_path, "vmr", "10.0.14", f'_commit="{COMMIT}"\n')
    package(tmp_path, "file", "1.2.3", f"_sdk={COMMIT}\n")
    package(tmp_path, "unpinned", "1.0", "")
    monkeypatch.setattr(pins, "described_commit", lambda srcinfo, version: f"described {version}")
    monkeypatch.setattr(pins, "nuget_commit", lambda package, pkgbuild, version: f"nuget {version}")
    monkeypatch.setattr(pins, "vmr_commit", lambda version, path: f"vmr {version} {path}")
    monkeypatch.setattr(pins, "file_value", lambda url, pattern: f"file {url}")
    return Checkout(tmp_path, tmp_path)


def test_resolve_pins_by_package(checkout: Checkout) -> None:
    assert pins.resolve_pins(checkout, "described") == [("_commit", "described 2.2.r84.g5b0aa72")]
    assert pins.resolve_pins(checkout, "nuget") == [("_commit", "nuget 1.0.0")]
    assert pins.resolve_pins(checkout, "vmr") == [("_commit", "vmr 10.0.14 runtime")]
    assert pins.resolve_pins(checkout, "file") == [("_sdk", "file https://x/v1.2.3")]
    assert pins.resolve_pins(checkout, "unpinned") == []


def test_reading_the_pkgbuild(checkout: Checkout) -> None:
    pkgbuild = "_packages=(\n  'Microsoft.Identity.Client'\n  Other\n)\n_sdks=(a b\n  c)\n"
    assert pins.array_first(pkgbuild, "_packages") == "Microsoft.Identity.Client"
    assert pins.array(pkgbuild, "_sdks") == ["a", "b", "c"]
    assert pins.array_first(pkgbuild, "_missing") == ""
    srcinfo = Srcinfo.load(checkout.root / "described")
    assert pins.github_repository(srcinfo) == "owner/described"
    git = Srcinfo.parse("pkgbase = x\n\tsource = git+https://github.com/a/b.git#commit=abc\n")
    assert pins.github_repository(git) == "a/b"


def test_set_pin_changes_its_line_only(tmp_path: Path) -> None:
    pkgbuild = tmp_path / "PKGBUILD"
    pkgbuild.write_text("pkgver=20261108\npkgrel=3\n_commit_a=aaa\n_commit_b='bbb'\n_commit_c=ccc\n")
    pins.set_pin(pkgbuild, "_commit_b", "new")
    pins.set_pin(pkgbuild, "_commit_a", "x")
    assert pkgbuild.read_text() == "pkgver=20261108\npkgrel=3\n_commit_a=x\n_commit_b='new'\n_commit_c=ccc\n"
    pins.set_pin(pkgbuild, "pkgver", "20261115")
    assert pkgbuild.read_text().startswith("pkgver=20261115\npkgrel=1\n_commit_a=x\n")
    assert pins.pin_value(pkgbuild, "_commit_c") == "ccc"
