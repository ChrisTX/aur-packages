"""The PGP keys the packages ship and need, offline, with temporary keyrings."""

import shutil
from pathlib import Path

import pytest

from aur_packages import keys
from aur_packages.repo import Checkout

ROOT = Path(__file__).resolve().parent.parent
# The key of the OWASP Core Rule Set, which modsecurity-crs ships
KEY = "36006F0E0BA167832158821138EEACA1AB8A6E72"
OTHER = "B5D6953E6D5059ED7ADA0F2FD3657D24D058434C"
# The PMD Release Signing Key, which local/pmd ships, and its signing subkey
PMD = "2EFA55D0785C31F956F2F87EA0B5CA1A4E086838"
PMD_SUBKEY = "1E046C19ED2873D8C08AF7B8A0632691B78E3422"


def package(root: Path, name: str, validpgpkeys: list[str], files: dict[str, str]) -> Path:
    folder = root / name
    (folder / "keys" / "pgp").mkdir(parents=True)
    (folder / "PKGBUILD").write_text("")
    lines = "".join(f"\tvalidpgpkeys = {key}\n" for key in validpgpkeys)
    (folder / ".SRCINFO").write_text(f"pkgbase = {name}\n{lines}\npkgname = {name}\n")
    for name_, source in files.items():
        shutil.copy(ROOT / source, folder / "keys" / "pgp" / f"{name_}.asc")
    return folder


@pytest.fixture
def checkout(tmp_path: Path) -> Checkout:
    shipped = f"modsecurity-crs/keys/pgp/{KEY}.asc"
    package(tmp_path, "good", [KEY], {KEY: shipped})
    package(tmp_path, "missing", [KEY], {})
    package(tmp_path, "stray", [KEY], {KEY: shipped, OTHER: f"lib32-jansson/keys/pgp/{OTHER}.asc"})
    # A file whose name says another key than it has
    package(tmp_path, "wrong", [OTHER], {OTHER: shipped})
    # validpgpkeys with a subkey, which makepkg doesn't accept
    package(tmp_path, "subkey", [PMD_SUBKEY], {PMD_SUBKEY: f"local/pmd/keys/pgp/{PMD}.asc"})
    return Checkout(tmp_path, tmp_path)


def test_run_keys(checkout: Checkout, capsys: pytest.CaptureFixture[str]) -> None:
    assert keys.run_keys(checkout, ["good/.SRCINFO"], fetch=False) == 0
    for name, message in [
        ("missing", f"keys/pgp/{KEY}.asc is missing"),
        ("stray", f"keys/pgp/{OTHER}.asc isn't one of validpgpkeys"),
        ("wrong", f"keys/pgp/{OTHER}.asc doesn't have the primary key {OTHER}"),
        ("subkey", f"keys/pgp/{PMD_SUBKEY}.asc doesn't have the primary key {PMD_SUBKEY}"),
    ]:
        assert keys.run_keys(checkout, [name], fetch=False) == 1
        assert message in capsys.readouterr().out


def test_prepare_imports_the_shipped_keys(checkout: Checkout, tmp_path: Path) -> None:
    home = tmp_path / "keyring"
    keys.prepare([checkout.root / "good"], home, fetch=False)
    assert keys.has(home, KEY)


def test_prepare_stops_with_the_missing_keys(checkout: Checkout, tmp_path: Path) -> None:
    with pytest.raises(keys.MissingKeys, match=f"{KEY}: missing"):
        keys.prepare([checkout.root / "missing"], tmp_path / "keyring", fetch=False)
