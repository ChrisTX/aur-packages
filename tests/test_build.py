"""The build order, the multilib containers and the configurations of the builds."""

from pathlib import Path

import pytest

from aur_packages import build
from aur_packages.repo import Checkout, SelectionError

SRCINFO = {
    # dotnet-build-deps-10.0 is both a package and provided by the -bin selector: the package wins
    "selector": "pkgbase = selector\n\tpkgver = 1\n\tpkgrel = 1\n\narch = any\npkgname = dotnet-build-deps-10.0\n",
    "selector-bin": (
        "pkgbase = selector-bin\n\tpkgver = 1\n\tpkgrel = 1\n\tarch = any\n\n"
        "pkgname = selector-bin\n\tprovides = dotnet-build-deps-10.0=1\n"
    ),
    "lib": "pkgbase = lib\n\tpkgver = 1\n\tpkgrel = 1\n\tarch = x86_64\n\tdepends = lib32-glibc\n\npkgname = lib\n",
    "app": (
        "pkgbase = app\n\tpkgver = 1\n\tpkgrel = 1\n\tarch = x86_64\n\tarch = aarch64\n"
        "\tmakedepends = dotnet-build-deps-10.0>=1\n\tdepends_x86_64 = lib\n\tdepends = glibc\n\n"
        "pkgname = app\n\npkgname = app-docs\n"
    ),
    "lone": "pkgbase = lone\n\tpkgver = 1\n\tpkgrel = 1\n\tarch = any\n\npkgname = lone\n",
}


@pytest.fixture
def checkout(tmp_path: Path) -> Checkout:
    for folder, srcinfo in SRCINFO.items():
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "PKGBUILD").write_text("")
        (tmp_path / folder / ".SRCINFO").write_text(srcinfo)
    return Checkout(tmp_path, tmp_path)


def test_edges(checkout: Checkout) -> None:
    assert build.edges(checkout, {}) == {("selector", "app"), ("lib", "app")}
    # --dotnet-bin redirects the name to the -bin selector
    assert build.edges(checkout, {"dotnet-build-deps-10.0": "selector-bin"}) == {
        ("selector-bin", "app"),
        ("lib", "app"),
    }


def test_order(checkout: Checkout) -> None:
    graph = build.edges(checkout, {})
    order = build.order(checkout, ["app", "lone"], graph)
    assert order[-2:] == ["app", "lone"]
    assert sorted(order[:2]) == ["lib", "selector"]
    assert build.order(checkout, ["lib"], graph) == ["lib"]


def test_multilib_through_a_dependency(checkout: Checkout) -> None:
    graph = build.edges(checkout, {})
    assert build.multilib(checkout, "lib", graph)
    assert build.multilib(checkout, "app", graph)
    assert not build.multilib(checkout, "lone", graph)


def test_roots(checkout: Checkout) -> None:
    assert build.roots(checkout, ["app/", "lone"]) == ["app", "lone"]
    with pytest.raises(SelectionError, match="Not a template or package: nope"):
        build.roots(checkout, ["nope"])


def test_architectures(checkout: Checkout) -> None:
    assert build.architectures(checkout.root / "app") == ["x86_64", "aarch64"]


def test_sanitise_makepkg_conf(tmp_path: Path) -> None:
    conf = tmp_path / "makepkg.conf"
    conf.write_text("CFLAGS=-O2\n")
    text = build.sanitise_makepkg_conf(conf, "address,undefined")
    assert text.startswith("CFLAGS=-O2\n")
    assert 'CFLAGS+=" -fsanitize=address,undefined -fno-omit-frame-pointer -fno-sanitize=' in text
    assert "-fno-sanitize" not in build.sanitise_makepkg_conf(conf, "address")


def test_alarm_pacman_conf_with_the_private_repository() -> None:
    text = build.alarm_pacman_conf(Path("/alarm"), ("aur-build", Path("/repo")))
    assert "CacheDir = /alarm/pkgcache\n" in text
    # The private repository comes before Arch Linux ARM's
    assert text.index("[aur-build]\nSigLevel = Never\nServer = file:///repo\n") < text.index("[core]")


def test_validate_refuses() -> None:
    with pytest.raises(build.BuildError, match="need a chroot build"):
        build.validate(build.Build(method="local", testing=True))
    with pytest.raises(build.BuildError, match="Unknown target"):
        build.validate(build.Build(target="sparc"))
    with pytest.raises(build.BuildError, match="are for the packages --add adds"):
        # local: CI has makepkg, but not aurutils, which a chroot build requires first
        build.validate(build.Build(method="local", signing=True))
