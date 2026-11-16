"""The PGP keys that verify the sources of the packages (validpgpkeys).

Each package ships the keys it lists, as keys/pgp/<fingerprint>.asc like Arch Linux's packaging
(export-pkgbuild-keys), so that its sources can be verified without a keyserver, also once a key is
no longer available there. keys checks that (the hook), keys --fetch adds the missing ones.

Before building, build and sysupgrade check that the keyring makepkg will use has every key the
packages need: they import the keys this repository ships, and stop with the missing ones, or with
-K (--auto-key-retrieve) fetch those from a keyserver, like aur sync -K. Chroot builds use the
keyring of aur sync -K ($AUR_SYNC_GNUPGHOME), which aur build passes to makepkg; the builder's own
keyring stays as it is.
"""

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from aur_packages.repo import Checkout
from aur_packages.tools import require

KEYSERVERS = ("hkps://keyserver.ubuntu.com", "hkps://keys.openpgp.org")


class MissingKeys(Exception):
    """Keys the packages need that the keyring doesn't have."""


def needed(folder: Path) -> list[str]:
    """The fingerprints a package's .SRCINFO lists in validpgpkeys, in all its sections."""
    srcinfo = folder / ".SRCINFO"
    if not srcinfo.exists():
        return []
    keys = []
    for line in srcinfo.read_text().splitlines():
        key, _, value = line.strip().partition(" = ")
        if key == "validpgpkeys" and value not in keys:
            keys.append(value.upper())
    return keys


# The protocols of makepkg's verify_<protocol>_signature, which verify a source with ?signed
SIGNED_PROTOCOLS = ("git", "file")


def signed(entry: str) -> bool:
    """Whether makepkg verifies a source's signature, by its source_has_signatures: a file named
    .sig, .sign or .asc, or ?signed on a source of a protocol it can verify (a git tag or commit)."""
    name = entry.split("::", 1)[0]
    if re.search(r"\.(sig|sign|asc)$", name):
        return True
    url = entry.split("::", 1)[-1]
    protocol = url.split("://", 1)[0].split("+", 1)[0] if "://" in url else "local"
    return protocol in SIGNED_PROTOCOLS and url.partition("?")[2] == "signed"


def has_signed_source(folder: Path) -> bool:
    """Whether a package has a source makepkg verifies, for any architecture: without one, makepkg
    ignores validpgpkeys and verifies nothing, without saying so."""
    srcinfo = folder / ".SRCINFO"
    if not srcinfo.exists():
        return False
    for line in srcinfo.read_text().splitlines():
        key, _, value = line.strip().partition(" = ")
        if re.fullmatch(r"source(_\w+)?", key) and signed(value):
            return True
    return False


def shipped(folder: Path, fingerprint: str) -> Path:
    return folder / "keys" / "pgp" / f"{fingerprint}.asc"


def file_fingerprints(path: Path) -> list[str]:
    """The fingerprints of the primary keys in a file, read without a keyring: makepkg compares
    validpgpkeys with the primary key's, also for a signature of a subkey."""
    result = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--show-keys", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    # The record right after a primary key's (pub) is its fingerprint: 40 hexadecimal digits in its
    # tenth field; those of the subkeys follow their own records (sub)
    found = []
    previous = ""
    for line in result.stdout.splitlines():
        fields = line.split(":")
        if previous == "pub" and len(fields) > 9 and re.fullmatch(r"[0-9A-F]{40}", fields[9]):
            found.append(fields[9])
        previous = fields[0]
    return found


def keyring() -> Path:
    """The keyring of aur sync -K, $AUR_SYNC_GNUPGHOME, which makepkg verifies chroot builds with."""
    if home := os.environ.get("AUR_SYNC_GNUPGHOME"):
        return Path(home)
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data / "aurutils" / "aur-sync" / "gnupg"


def gpg(home: Path | None, *arguments: str) -> subprocess.CompletedProcess[str]:
    """gpg with a keyring, or the user's own with None."""
    env = {**os.environ, "GNUPGHOME": str(home)} if home is not None else None
    return subprocess.run(
        ["gpg", "--batch", *arguments], capture_output=True, text=True, env=env, check=False
    )


def has(home: Path | None, fingerprint: str) -> bool:
    return gpg(home, "--list-keys", fingerprint).returncode == 0


def receive(home: Path, fingerprint: str) -> bool:
    """Fetch a key into a keyring by its fingerprint, from the first keyserver that has it."""
    for server in KEYSERVERS:
        gpg(home, "--keyserver", server, "--recv-keys", fingerprint)
        if has(home, fingerprint):
            return True
    return False


def prepare(folders: Iterable[Path], home: Path | None, fetch: bool) -> None:
    """Make sure a keyring has the keys the packages need, before anything is built.

    Imports the keys the packages ship into it (not into the user's own keyring, None, which is
    only checked), and with fetch the others from a keyserver; raises MissingKeys with the keys
    still missing and the packages that need them.
    """
    wanted: dict[str, list[Path]] = {}
    for folder in folders:
        for fingerprint in needed(folder):
            wanted.setdefault(fingerprint, []).append(folder)
    if not wanted:
        return
    require("build", [("gpg", "gnupg")])
    if home is not None:
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
    missing = {}
    for fingerprint, users in wanted.items():
        if has(home, fingerprint):
            continue
        files = [shipped(folder, fingerprint) for folder in users if shipped(folder, fingerprint).exists()]
        if home is not None and files:
            gpg(home, "--import", str(files[0]))
        if home is not None and not has(home, fingerprint) and fetch:
            print(f">>> Fetching the key {fingerprint} from a keyserver", file=sys.stderr)
            receive(home, fingerprint)
        if not has(home, fingerprint):
            missing[fingerprint] = users
    if missing:
        where = f"the keyring {home}" if home is not None else "your keyring"
        lines = [f"These PGP keys, which verify the sources, aren't in {where}:"]
        for fingerprint, users in missing.items():
            lines.append(f"  {fingerprint}: {', '.join(folder.name for folder in users)}")
        if home is not None:
            lines.append("Fetch them from a keyserver with -K (--auto-key-retrieve), or import them with")
            lines.append(f"  GNUPGHOME={home} gpg --recv-keys FINGERPRINT")
        else:
            lines.append("Import them into your keyring, e.g. gpg --recv-keys FINGERPRINT")
        raise MissingKeys("\n".join(lines))


def aur_queue(names: Sequence[str], options: Sequence[str] = ()) -> list[Path]:
    """The folders of the packages aur sync would build for names, with their AUR dependencies,
    fetched by it without building (--no-build)."""
    if not names and "--upgrades" not in options:
        return []
    result = subprocess.run(
        ["aur", "sync", "--no-build", "--no-view", "--noconfirm", *options, *names],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    return [Path(line) for line in result.stdout.splitlines() if line.startswith("/")]


def run_keys(checkout: Checkout, paths: Sequence[str], fetch: bool) -> int:
    """That each package ships the keys of its validpgpkeys, and only those (the hook); with fetch,
    add the missing ones, from a keyserver through a temporary keyring, as export-pkgbuild-keys."""
    status = 0
    names = [re.sub(r"/(\.SRCINFO|PKGBUILD|keys/pgp/[^/]+)$", "", path) for path in paths]
    for name in checkout.select(list(dict.fromkeys(names))):
        folder = checkout.root / name
        keys = needed(folder)
        # Both directions: makepkg doesn't say either, and the second one builds for whoever trusts
        # the key in their own keyring, and fails for everyone else
        verified = has_signed_source(folder)
        if keys and not verified:
            print(
                f"{name}: validpgpkeys without a signed source (?signed, or a .sig, .sign or .asc file): "
                "makepkg verifies nothing"
            )
            status = 1
        elif verified and not keys:
            print(
                f"{name}: a signed source without validpgpkeys: makepkg only accepts the keys a keyring "
                "trusts, so the build fails for others"
            )
            status = 1
        for fingerprint in keys:
            path = shipped(folder, fingerprint)
            if not path.exists() and fetch:
                status |= add(folder, fingerprint)
            elif not path.exists():
                print(f"{name}: keys/pgp/{fingerprint}.asc is missing: ./aur-packages keys --fetch {name}")
                status = 1
            elif fingerprint not in file_fingerprints(path):
                # makepkg compares validpgpkeys with the primary key's fingerprint, also for a
                # signature of one of its subkeys
                print(f"{name}: keys/pgp/{fingerprint}.asc doesn't have the primary key {fingerprint}")
                status = 1
        # Arch Linux's packaging in overrides/ keeps the keys it has, e.g. of earlier sources
        stray = [] if name.startswith("overrides/") else sorted((folder / "keys" / "pgp").glob("*.asc"))
        for path in stray:
            if path.stem not in keys:
                print(f"{name}: keys/pgp/{path.name} isn't one of validpgpkeys")
                status = 1
    return status


def add(folder: Path, fingerprint: str) -> int:
    """Ship a key: fetched into a temporary keyring, exported minimal like export-pkgbuild-keys."""
    require("keys --fetch", [("gpg", "gnupg")])
    with tempfile.TemporaryDirectory(prefix="aur-packages-keys.") as home:
        if not receive(Path(home), fingerprint):
            print(f"{folder.name}: no keyserver has the key {fingerprint}", file=sys.stderr)
            return 1
        exported = gpg(
            Path(home), "--armor", "--export", "--export-options", "export-minimal", fingerprint
        ).stdout
    path = shipped(folder, fingerprint)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(exported)
    print(f"{folder.name}: added keys/pgp/{fingerprint}.asc")
    return 0
