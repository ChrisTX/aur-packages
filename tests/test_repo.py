"""The packages of a checkout and their selection."""

from pathlib import Path

import pytest

from aur_packages.repo import Checkout, SelectionError


@pytest.fixture
def checkout(tmp_path: Path) -> Checkout:
    for folder in ("beta", "alpha", "local/gamma", "overrides/delta", "notapackage"):
        (tmp_path / folder).mkdir(parents=True)
        if folder != "notapackage":
            (tmp_path / folder / "PKGBUILD").write_text("pkgname=x\n")
    return Checkout(tmp_path, tmp_path)


def test_package_dirs(checkout: Checkout) -> None:
    assert checkout.package_dirs() == ["alpha", "beta", "local/gamma", "overrides/delta"]


def test_package_dir_by_folder_or_name(checkout: Checkout) -> None:
    assert checkout.package_dir("alpha/") == "alpha"
    assert checkout.package_dir("gamma") == "local/gamma"
    assert checkout.package_dir("local/gamma") == "local/gamma"
    assert checkout.package_dir("delta") == "overrides/delta"
    assert checkout.package_dir("notapackage") is None


def test_select_all(checkout: Checkout) -> None:
    assert checkout.select([]) == checkout.package_dirs()
    assert checkout.select([], aur_only=True) == ["alpha", "beta"]


def test_select_given(checkout: Checkout) -> None:
    assert checkout.select(["gamma", "beta"]) == ["local/gamma", "beta"]


def test_select_refuses(checkout: Checkout) -> None:
    with pytest.raises(SelectionError, match="Not a package: nope"):
        checkout.select(["nope"])
    with pytest.raises(SelectionError, match="Not an AUR package: local/gamma"):
        checkout.select(["gamma"], aur_only=True)
