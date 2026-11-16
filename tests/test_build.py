"""The build order, the multilib containers and the configurations of the builds."""

import io
import tarfile
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


def test_cross_ready(checkout: Checkout) -> None:
    app = checkout.root / "app"
    # Not for aarch64 (x86_64 only, any): nothing to cross-build
    assert build.cross_ready(checkout.root / "lib")
    assert build.cross_ready(checkout.root / "lone")
    # For aarch64, building nothing (prebuilt sources, a selector)
    assert build.cross_ready(app)
    # Compiling, but not for $CARCH: the compilers would build for x86_64
    (app / "PKGBUILD").write_text("build() {\n  go build\n}\n")
    assert not build.cross_ready(app)
    for ready in (
        'build() {\n  case "$CARCH" in aarch64) rid=arm64 ;; esac\n}\n',
        'build() {\n  cc --sysroot="${ROOTFS_DIR}" x.c\n}\n',
        "source_aarch64=(x-arm64.tar.gz)\nbuild() {\n  make\n}\n",
    ):
        (app / "PKGBUILD").write_text(ready)
        assert build.cross_ready(app)


def test_cross_built(tmp_path: Path) -> None:
    def elf(machine: int) -> bytes:
        # Little endian (EI_DATA 1), e_machine at offset 18
        return b"\x7fELF\x02\x01" + bytes(12) + machine.to_bytes(2, "little") + bytes(44)

    package = tmp_path / "x-1-1-aarch64.pkg.tar.gz"
    with tarfile.open(package, "w:gz") as archive:
        for name, content in [
            ("usr/bin/good", elf(183)),
            ("usr/bin/wrong", elf(62)),
            ("usr/share/doc/x/README", b"text, not an ELF file at all"),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    assert build.cross_built(package) == ["usr/bin/wrong (x86_64)"]


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


def test_package_files(tmp_path: Path) -> None:
    names = [
        "app-1.0-1-x86_64.pkg.tar.zst",
        "app-1.0-1-x86_64.pkg.tar.zst.sig",
        "app-debug-1.0-1-x86_64.pkg.tar.xz",
        "app-docs-2:1.0-1-any.pkg.tar",
        "dotnet-sdk-10.0-bin-10.0.0.sdk100-3-x86_64.pkg.tar.gz",
        "dotnet-sdk-bin-11.0.0.sdk100-1-x86_64.pkg.tar.lz4",
        "app-1.0-1-x86_64.pkg.tar.unknown",
    ]
    for name in names:
        (tmp_path / name).touch()
    assert [f.name for f in build.package_files(tmp_path, "app")] == ["app-1.0-1-x86_64.pkg.tar.zst"]
    assert [f.name for f in build.package_files(tmp_path, "dotnet-sdk-bin")] == [
        "dotnet-sdk-bin-11.0.0.sdk100-1-x86_64.pkg.tar.lz4"
    ]
    # Every package file, compressed or not, without signatures and unknown extensions
    assert len(build.package_files(tmp_path)) == 5


def test_install_as_root_with_aur_pacman_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # env stands in for sudo or run0: it runs the command with its own options
    monkeypatch.setenv("AUR_PACMAN_AUTH", "env AUR_PACKAGES_TEST=1")
    assert build.auth() == ["env", "AUR_PACKAGES_TEST=1"]
    build.install_as_root("[options]\n", tmp_path / "pacman.conf")
    assert (tmp_path / "pacman.conf").read_text() == "[options]\n"
    monkeypatch.setenv("AUR_PACMAN_AUTH", "")
    assert build.auth() == ["sudo"]
