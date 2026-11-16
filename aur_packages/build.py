"""Building packages with their dependencies from this repository, in clean chroots (aurutils).

Builds go into a private throwaway repository, from which each build resolves the packages built
before it, so they don't touch the system's aurutils repository; build --add adds them to that one at
the end, and sysupgrade does that for our packages before aur sync -u updates the rest.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from aur_packages import keys
from aur_packages.repo import BUILD_TEMPLATES, Checkout, SelectionError
from aur_packages.srcinfo import Srcinfo
from aur_packages.tools import require

REPO_NAME = "aur-build"
CROSS_NAME = "aur-build-aarch64"
DEVTOOLS = Path("/usr/share/devtools")
MAKEPKG_CONF = DEVTOOLS / "makepkg.conf.d" / "x86_64.conf"
# The key of the Arch Linux ARM build system, which signs its images
ALARM_KEY = "68B3537F39A313B3E574D06777193F152BDBE6A6"
# Arch Linux 32's master keys, the trusted ones of archlinux32-keyring (archlinux32-trusted), which
# certify its packagers' keys: Erich Eckner, Balló György, Polichronucci, Tyler Dence, Andreas Baumann
ARCHLINUX32_MASTER_KEYS = (
    "194E37A47A4C671807BACB37B1117BC1094EA6E9",
    "CE0BDE71A759A87F23F0F7D8B61DBCE10901C163",
    "A0B250C0FC9FC079EC04ADB7A50C0F20AEC3AF00",
    "D92CDDC155BCC8F550B5FCEC30AB721FE7400FCD",
    "C426F2CED2D759ECEA1FA78A4BA3B2E330891150",
)
ARCHLINUX32_MIRROR = "https://mirror.archlinux32.org/$arch/$repo"
# The targets of build --target: the CARCH their packages are for, and what they do
TARGETS = {
    "aarch64": ("aarch64", "cross-builds for aarch64"),
    "aarch64-native": ("aarch64", "builds in Arch Linux ARM under QEMU"),
    "i686": ("i686", "builds in Arch Linux 32"),
}
# The packages of the commands $AUR_PACMAN_AUTH may name
AUTH_PACKAGES = {"sudo": "sudo", "sudo-rs": "sudo-rs", "run0": "systemd", "doas": "opendoas"}
DEPENDS = re.compile(r"^(depends|makedepends|checkdepends)(_\w+)?$")


class BuildError(Exception):
    """A build step that failed; its exit code is the command's."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def srcinfo_lines(package: Path) -> list[tuple[str, str]]:
    """The keys and values of a .SRCINFO in their order, of every section."""
    lines = []
    for line in (package / ".SRCINFO").read_text().splitlines():
        key, separator, value = line.strip().partition(" = ")
        if separator:
            lines.append((key, value))
    return lines


def bare(name: str) -> str:
    """A dependency's name without its version constraint or description."""
    return re.split(r"[<>=:]", name, maxsplit=1)[0]


def edges(checkout: Checkout, alias: dict[str, str]) -> set[tuple[str, str]]:
    """(dependency, dependent) for every build dependency on another package of this repository.

    depends, makedepends and checkdepends, of any architecture. A package's own name wins over what
    others provide, e.g. dotnet-build-deps-10.0 over the dotnet-build-deps-10.0-bin that provides it;
    alias redirects names, as --dotnet-bin and --nuget-bin do.
    """
    folders = checkout.package_dirs()
    name_dir: dict[str, str] = {}
    provided: set[str] = set()
    for folder in folders:
        for key, value in srcinfo_lines(checkout.root / folder):
            name = bare(value)
            if not name:
                continue
            if key == "pkgname":
                name_dir[name] = folder
                provided.discard(name)
            elif key == "provides" and (name not in name_dir or name in provided):
                name_dir[name] = folder
                provided.add(name)
    name_dir.update(alias)
    result = set()
    for folder in folders:
        for key, value in srcinfo_lines(checkout.root / folder):
            if DEPENDS.match(key) and (dep := name_dir.get(bare(value))) and dep != folder:
                result.add((dep, folder))
    return result


def order(checkout: Checkout, roots: Sequence[str], graph: set[tuple[str, str]]) -> list[str]:
    """The roots and all their dependencies of this repository, dependencies first (tsort)."""
    deps: dict[str, list[str]] = {}
    for dep, dependent in sorted(graph):
        deps.setdefault(dependent, []).append(dep)
    seen: list[str] = []
    queue = list(roots)
    while queue:
        package = queue.pop(0)
        if package in seen:
            continue
        seen.append(package)
        queue += [d for d in deps.get(package, []) if d not in seen]
    induced = "".join(f"{a}\t{b}\n" for a, b in sorted(graph) if a in seen and b in seen)
    ordered = subprocess.run(
        ["tsort"], input=induced, capture_output=True, text=True, check=True
    ).stdout.split()
    # Packages without dependency edges don't appear in tsort's order; theirs is free
    return ordered + [p for p in seen if p not in ordered]


def multilib(checkout: Checkout, package: str, graph: set[tuple[str, str]]) -> bool:
    """Whether a package builds against multilib: it or a dependency of ours needs lib32-* packages.

    Like Arch's multilib packages (pkgctl build --repo multilib), it builds in a container of its own
    with multilib and its toolchain (multilib-devel).
    """
    lib32 = re.compile(r"^\s*(depends|makedepends|checkdepends)(_x86_64)? = lib32-", re.MULTILINE)
    seen: set[str] = set()
    queue = [package]
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if lib32.search((checkout.root / current / ".SRCINFO").read_text()):
            return True
        queue += [dep for dep, dependent in graph if dependent == current]
    return False


def aur_only_deps(checkout: Checkout, repoconf: Path, packages: Sequence[str]) -> list[str]:
    """The dependencies of the packages that only the AUR has.

    Neither a package of this repository (by name or provides), nor in the official repositories of a
    pacman.conf of devtools (with the host's sync databases, without dependency checks, which would
    weigh in the host's installed packages): e.g. lasso for sogo, or the .NET SDK of a -bin selector.
    """
    ours = {
        bare(value)
        for folder in checkout.package_dirs()
        for key, value in srcinfo_lines(checkout.root / folder)
        if key in ("pkgname", "provides")
    }
    wanted = {
        bare(value)
        for folder in packages
        for key, value in srcinfo_lines(checkout.root / folder)
        if DEPENDS.match(key) and bare(value) and bare(value) not in ours
    }
    return sorted(
        name
        for name in wanted
        if subprocess.run(
            ["pacman", "--config", str(repoconf), "-Sddp", "--print-format", "%n", name],
            capture_output=True,
            check=False,
        ).returncode
    )


# A package file as makepkg names it, NAME-PKGVER-PKGREL-ARCH and its PKGEXT: .pkg.tar, compressed
# with any of the compressions makepkg.conf offers, or not
PACKAGE_FILE = re.compile(r"^(?P<name>.+)-[^-]+-[^-]+-[^-]+\.pkg\.tar(\.(gz|bz2|xz|zst|lzo|lrz|lz4|lz|Z))?$")


def package_files(repo: Path, name: str | None = None) -> list[Path]:
    """The package files in a repository folder, sorted; with name, only those of that package."""
    return sorted(
        file
        for file in repo.glob("*.pkg.tar*")
        if (match := PACKAGE_FILE.match(file.name)) and name in (None, match["name"])
    )


def repo_provides(repo: Path, name: str) -> bool:
    """Whether a package in a repository folder is called name or provides it."""
    pattern = re.compile(rf"^(pkgname|provides) = {re.escape(name)}([<>=].*)?$", re.MULTILINE)
    for file in package_files(repo):
        info = subprocess.run(
            ["bsdtar", "-xOf", str(file), ".PKGINFO"], capture_output=True, text=True, check=False
        )
        if pattern.search(info.stdout):
            return True
    return False


def devtools_pacman_conf(name: str, repo: Path, system: tuple[str, Path] | None = None) -> str:
    """A pacman.conf of devtools (extra.conf, …) with the private repository first, so its packages win,
    then the system's aurutils repository if given (--system-repo)."""
    out, inserted = [], False
    for line in (DEVTOOLS / "pacman.conf.d" / name).read_text().splitlines():
        if line.startswith("[") and line != "[options]" and not inserted:
            out += [f"[{REPO_NAME}]", "SigLevel = Never", f"Server = file://{repo}", ""]
            if system:
                out += [f"[{system[0]}]", "SigLevel = Never", f"Server = file://{system[1]}", ""]
            inserted = True
        out.append(line)
    return "\n".join(out) + "\n"


def alarm_pacman_conf(alarm: Path, repo: tuple[str, Path] | None = None) -> str:
    """The pacman.conf of the Arch Linux ARM root, with the mirrors (arch-nspawn writes the system's
    into the mirrorlist) and its own package cache; with a private repository first if given."""
    text = (
        f"[options]\nArchitecture = aarch64\nCacheDir = {alarm}/pkgcache\nHoldPkg = pacman glibc\n"
        "SigLevel = Required DatabaseOptional\nLocalFileSigLevel = Optional\nParallelDownloads = 5\n"
    )
    if repo:
        text += f"\n[{repo[0]}]\nSigLevel = Never\nServer = file://{repo[1]}\n"
    for name in ("core", "extra", "alarm", "aur"):
        text += f"\n[{name}]\nServer = http://mirror.archlinuxarm.org/$arch/$repo\n"
    return text


def target_block(conf: str, heading: str, target: str, lines: str) -> str:
    """A makepkg.conf with the lines of a target's builds at its end, under a comment.

    arch-nspawn copies the makepkg.conf into the root for each build, and the next one starts from
    the root's: the lines of the earlier builds are cut off first, by the start of their comment, as
    their end named the command differently before (./aur build).
    """
    start = conf.find(f"\n# {heading} (")
    return (conf if start < 0 else conf[:start]) + (
        f"\n# {heading} (./aur-packages build --target {target})\n{lines}"
    )


def alarm_makepkg_conf(alarm: Path) -> str:
    """The makepkg.conf of the native aarch64 builds, the root's, with CARCH exported.

    arch-nspawn would run setarch for a line starting with CARCH=, which an x86_64 kernel doesn't
    support for aarch64.
    """
    text = re.sub(
        r"^CARCH=", "export CARCH=", (alarm / "root" / "etc" / "makepkg.conf").read_text(), flags=re.MULTILINE
    )
    return target_block(
        text,
        "Native aarch64 build under QEMU",
        "aarch64-native",
        f'MAKEFLAGS="-j{os.cpu_count()}"\n'
        "# .NET's W^X double mapping fails under qemu-user\nexport DOTNET_EnableWriteXorExecute=0\n",
    )


def archlinux32_pacman_conf(
    a32: Path, repo: tuple[str, Path] | None = None, gpgdir: Path | None = None
) -> str:
    """The pacman.conf of the Arch Linux 32 root, like alarm_pacman_conf; with gpgdir, the keyring
    that mkarchroot verifies the packages of the new root with, from the host."""
    text = (
        f"[options]\nArchitecture = i686\nCacheDir = {a32}/pkgcache\nHoldPkg = pacman glibc\n"
        "SigLevel = Required DatabaseOptional\nLocalFileSigLevel = Optional\nParallelDownloads = 5\n"
    )
    if gpgdir:
        text += f"GPGDir = {gpgdir}\n"
    if repo:
        text += f"\n[{repo[0]}]\nSigLevel = Never\nServer = file://{repo[1]}\n"
    for name in ("core", "extra"):
        text += f"\n[{name}]\nServer = {ARCHLINUX32_MIRROR}\n"
    return text


def archlinux32_makepkg_conf(root_conf: str) -> str:
    """The makepkg.conf of the i686 builds, the root's.

    Its CARCH=i686 line stays: arch-nspawn runs the builds under setarch i686, so uname and the
    configure scripts that ask it see i686, which an x86_64 kernel runs natively.
    """
    return target_block(root_conf, "Native i686 build", "i686", f'MAKEFLAGS="-j{os.cpu_count()}"\n')


def repo_filename(database: Path, name: str) -> str:
    """The file name of a package in a repository's database (its desc's %FILENAME%)."""
    with tarfile.open(database) as archive:
        for member in archive:
            # NAME-PKGVER-PKGREL/desc
            if member.name.endswith("/desc") and member.name.removesuffix("/desc").rsplit("-", 2)[0] == name:
                content = archive.extractfile(member)
                desc = content.read().decode() if content else ""
                if match := re.search(r"^%FILENAME%\n(.+)$", desc, re.MULTILINE):
                    return match[1]
    raise BuildError(f"{name} isn't in {database}")


def cross_makepkg_conf(alarm: Path) -> str:
    """The makepkg.conf of cross builds for aarch64: devtools' for x86_64 with Arch Linux ARM's flags.

    The packages compile against the root (ROOTFS_DIR); makepkg strips and splits off debug
    information with binutils for aarch64, as functions for its own calls, and as OBJCOPY and
    READELF for gdb-add-index. CARCH is exported for arch-nspawn, see alarm_makepkg_conf.
    """
    devtools = "".join(
        line for line in MAKEPKG_CONF.read_text().splitlines(True) if not line.startswith("CARCH=")
    )
    flags = subprocess.run(
        ["bash", "-c", 'source "$1" && declare -p CHOST CFLAGS CXXFLAGS LDFLAGS LTOFLAGS', "bash",
         str(alarm / "root" / "etc" / "makepkg.conf")],
        capture_output=True, text=True, check=True,
    ).stdout.replace("declare -- ", "")  # fmt: skip
    return devtools + (
        "\n# Cross build for aarch64 (./aur-packages build --target aarch64)\nexport CARCH=aarch64\n"
        + flags
        + f"export ROOTFS_DIR={alarm}/root\n"
        'strip() { aarch64-linux-gnu-strip "$@"; }\nobjcopy() { aarch64-linux-gnu-objcopy "$@"; }\n'
        "export OBJCOPY=aarch64-linux-gnu-objcopy READELF=aarch64-linux-gnu-readelf\n"
    )


def sanitise_makepkg_conf(makepkg_conf: Path, sanitisers: str) -> str:
    """The makepkg.conf of test builds with the sanitisers (address, undefined or both).

    Without the checks of undefined that don't work for libraries loaded into closed-source programs,
    like the plugins of game servers (vptr and function need the whole program's type information),
    or that LLVM's LTO can't build for 32-bit x86 (pointer-overflow).
    """
    flags = f"-fsanitize={sanitisers} -fno-omit-frame-pointer"
    if "undefined" in sanitisers.split(","):
        flags += " -fno-sanitize=vptr,function,pointer-overflow"
    return makepkg_conf.read_text() + (
        f"\n# ./aur-packages build --sanitize={sanitisers}: test builds with the sanitisers\n"
        f'CFLAGS+=" {flags}"\nCXXFLAGS+=" {flags}"\nLDFLAGS+=" {flags}"\n'
        "export UBSAN_OPTIONS=print_stacktrace=1\n"
    )


def built_already(package: Path, repo: Path, makepkg_conf: Path) -> bool:
    """Whether the packages a folder builds are in the repository already, in their current version.

    makepkg lists a -debug package whenever debug is on, but only builds one with debug symbols.
    """
    files = subprocess.run(
        ["makepkg", "--packagelist", "--config", str(makepkg_conf)],
        cwd=package,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    debug = Srcinfo.load(package).pkgbase + "-debug-"
    found = False
    for file in files:
        name = Path(file).name
        if (repo / name).exists():
            found = True
        elif not name.startswith(debug):
            return False
    return found


def empty_database(repo: Path, name: str) -> None:
    """An empty database, so the first build can sync the repository before it has packages."""
    with tarfile.open(repo / f"{name}.db.tar.gz", "w:gz"):
        pass
    (repo / f"{name}.db").unlink(missing_ok=True)
    (repo / f"{name}.db").symlink_to(f"{name}.db.tar.gz")


def auth() -> list[str]:
    """The command that runs another as root: what $AUR_PACMAN_AUTH names, like for aurutils (sudo,
    sudo-rs, run0, doas, with their options), else sudo."""
    return shlex.split(os.environ.get("AUR_PACMAN_AUTH", "")) or ["sudo"]


def as_root(command: Sequence[str]) -> None:
    subprocess.run([*auth(), *command], check=True)


def install_as_root(text: str, target: Path) -> None:
    """Write a file owned by root, through a temporary file of ours rather than stdin, which not every
    command of AUR_PACMAN_AUTH passes on."""
    with tempfile.NamedTemporaryFile("w", prefix="aur-packages.") as file:
        file.write(text)
        file.flush()
        as_root(["install", "-m", "644", file.name, str(target)])


def download_cache(name: str) -> tuple[Path, Path]:
    """The folder of a root's downloads in the user's cache, and the GNUPGHOME that verifies them."""
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "aur-packages" / name
    gnupg = cache / "gnupg"
    gnupg.mkdir(parents=True, exist_ok=True)
    cache.chmod(0o700)
    gnupg.chmod(0o700)
    return cache, gnupg


def chroot_version() -> str:
    """The version of mkarchroot's marker (.arch-chroot), which arch-nspawn checks for."""
    return subprocess.run(
        ["bash", "-c", f"source {DEVTOOLS}/lib/archroot.sh && echo $CHROOT_VERSION"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def archlinux32_root(a32: Path) -> None:
    """Set up the Arch Linux 32 root in a32/root, unless it's there: the i686 builds run in it,
    natively. Arch Linux 32 has no current bootstrap tarball, so mkarchroot installs base-devel from
    its mirror, verified with the keyring of archlinux32-keyring, which a packager signs and the
    master keys of ARCHLINUX32_MASTER_KEYS have to certify."""
    if (a32 / "root").is_dir():
        return
    cache, gnupg = download_cache("archlinux32")
    core = ARCHLINUX32_MIRROR.replace("$arch", "i686").replace("$repo", "core")
    print(">>> Downloading Arch Linux 32's keyring", file=sys.stderr)
    subprocess.run(["curl", "-fL", "-o", str(cache / "core.db"), f"{core}/core.db"], check=True)
    package = repo_filename(cache / "core.db", "archlinux32-keyring")
    for file in (package, f"{package}.sig"):
        subprocess.run(["curl", "-fL", "-o", str(cache / file), f"{core}/{file}"], check=True)
    # Its keys, trusted only as far as the pinned master keys certify them
    keyring = cache / "keyring"
    shutil.rmtree(keyring, ignore_errors=True)
    keyring.mkdir()
    subprocess.run(["bsdtar", "-xf", str(cache / package), "-C", str(keyring), "usr/share/pacman/keyrings"], check=True)  # fmt: skip
    keyrings = keyring / "usr" / "share" / "pacman" / "keyrings"
    env = {**os.environ, "GNUPGHOME": str(gnupg)}
    subprocess.run(["gpg", "--batch", "--quiet", "--import", str(keyrings / "archlinux32.gpg")], env=env, check=True)  # fmt: skip
    subprocess.run(
        ["gpg", "--batch", "--import-ownertrust"],
        input="".join(f"{key}:6:\n" for key in ARCHLINUX32_MASTER_KEYS),
        text=True,
        env=env,
        check=True,
    )
    status = subprocess.run(
        ["gpg", "--batch", "--status-fd", "1", "--verify", str(cache / f"{package}.sig"), str(cache / package)],
        env=env, capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    if not re.search(r"^\[GNUPG:\] VALIDSIG ", status, re.MULTILINE) or not re.search(
        r"^\[GNUPG:\] TRUST_(FULLY|ULTIMATE)\b", status, re.MULTILINE
    ):
        raise BuildError(
            f"The signature of {cache / package} isn't valid, or not by a key Arch Linux 32's master keys certify"
        )
    print(f">>> Setting up the Arch Linux 32 root in {a32}/root", file=sys.stderr)
    as_root(["install", "-d", "-m", "755", str(a32), str(a32 / "pkgcache")])
    # The keyring mkarchroot verifies the packages with, on the host
    setup_gpgdir, setup_conf = a32 / "gnupg", a32 / "pacman-setup.conf"
    as_root(["pacman-key", "--gpgdir", str(setup_gpgdir), "--init"])
    as_root(["pacman-key", "--gpgdir", str(setup_gpgdir), "--populate-from", str(keyrings), "--populate", "archlinux32"])  # fmt: skip
    install_as_root(archlinux32_pacman_conf(a32, gpgdir=setup_gpgdir), setup_conf)
    as_root(["mkarchroot", "-C", str(setup_conf), "-c", str(a32 / "pkgcache"), str(a32 / "root"),
             "base-devel", "archlinux32-keyring"])  # fmt: skip
    # And the root's own, for its upgrades
    conf = a32 / "pacman.conf"
    install_as_root(archlinux32_pacman_conf(a32), conf)
    as_root(["arch-nspawn", "-C", str(conf), str(a32 / "root"), "sh", "-c",
             "pacman-key --init && pacman-key --populate archlinux32"])  # fmt: skip


def alarm_root(alarm: Path) -> None:
    """Set up the Arch Linux ARM root in alarm/root, unless it's there: the native builds run in it
    (under QEMU), the cross builds compile against it. From archlinuxarm.org's latest image, checked
    against its build system's key, without kernel and firmware, with base-devel, and without the
    image's user."""
    if (alarm / "root").is_dir():
        remove_image_user(alarm)
        return
    cache, gnupg = download_cache("alarm")
    image, url = "ArchLinuxARM-aarch64-latest.tar.gz", "http://os.archlinuxarm.org/os"
    print(">>> Downloading the Arch Linux ARM image", file=sys.stderr)
    subprocess.run(
        [
            "curl",
            "-fL",
            "--remote-time",
            "-z",
            str(cache / image),
            "-o",
            str(cache / image),
            f"{url}/{image}",
        ],
        check=True,
    )
    subprocess.run(["curl", "-fL", "-o", str(cache / f"{image}.sig"), f"{url}/{image}.sig"], check=True)
    env = {**os.environ, "GNUPGHOME": str(gnupg)}
    if subprocess.run(
        ["gpg", "--batch", "--list-keys", ALARM_KEY], env=env, capture_output=True, check=False
    ).returncode:
        subprocess.run(
            ["gpg", "--batch", "--keyserver", "hkps://keyserver.ubuntu.com", "--recv-keys", ALARM_KEY],
            env=env,
            check=True,
        )
    # A good signature by that key: its fingerprint ends the VALIDSIG status line
    status = subprocess.run(
        ["gpg", "--batch", "--status-fd", "1", "--verify", str(cache / f"{image}.sig"), str(cache / image)],
        env=env, capture_output=True, text=True, check=False,
    ).stdout  # fmt: skip
    if not re.search(rf"^\[GNUPG:\] VALIDSIG .* {ALARM_KEY}$", status, re.MULTILINE):
        raise BuildError(f"The signature of {cache / image} isn't valid")
    print(f">>> Setting up the Arch Linux ARM root in {alarm}/root", file=sys.stderr)
    as_root(["install", "-d", "-m", "755", str(alarm / "root"), str(alarm / "pkgcache")])
    as_root(["bsdtar", "-xpf", str(cache / image), "-C", str(alarm / "root")])
    conf = alarm / "pacman.conf"
    install_as_root(alarm_pacman_conf(alarm), conf)
    as_root(["systemd-nspawn", "-q", "-D", str(alarm / "root"), "sh", "-c",
             "pacman-key --init && pacman-key --populate archlinuxarm"])  # fmt: skip
    install_as_root(chroot_version(), alarm / "root" / ".arch-chroot")
    # -s: arch-nspawn would run setarch aarch64 for the CARCH of the image's makepkg.conf
    as_root(["arch-nspawn", "-s", "-C", str(conf), str(alarm / "root"), "sh", "-c",
             'pacman -Rdd --noconfirm linux-aarch64 $(pacman -Qqs "^linux-firmware") && pacman -Syu --noconfirm --needed base-devel'])  # fmt: skip
    remove_image_user(alarm)


def remove_image_user(alarm: Path) -> None:
    """Remove the user of Arch Linux ARM's image, alarm, from the root, which has the uid 1000.

    makechrootpkg adds its builduser with the builder's uid, often 1000 as well: sudo then knows the
    uid as alarm, so builduser's rule for pacman doesn't apply, and makepkg can't install the
    makedepends (sudo asks for a password). makechrootpkg copies the root for each build.
    """
    if re.search(r"^alarm:", (alarm / "root" / "etc" / "passwd").read_text(), re.MULTILINE):
        print(f">>> Removing the image's user alarm from {alarm}/root", file=sys.stderr)
        as_root(["systemd-nspawn", "-q", "-D", str(alarm / "root"), "userdel", "--remove", "alarm"])


@dataclass
class SystemRepo:
    """The system's aurutils repository, the one aur repo picks ($AUR_REPO, else the only file:// one)."""

    name: str
    root: Path
    db: Path

    @classmethod
    def find(cls) -> SystemRepo:
        status = subprocess.run(
            ["aur", "repo", "--status"], capture_output=True, text=True, check=True
        ).stdout
        fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
        return cls(fields["repo"], Path(fields["root"]), Path(fields["path"]))

    def signed(self) -> bool:
        return (self.root / f"{self.name}.db.sig").exists()

    def signing(self, requested: bool | None) -> bool:
        """Whether to sign: as --sign or --no-sign say, else if the database is or makepkg signs."""
        if requested is not None:
            return requested
        if self.signed():
            print(f"Signing the packages, the database of {self.name} is signed", file=sys.stderr)
            return True
        if makepkg_signs():
            print("Signing the packages, as makepkg does (sign in BUILDENV)", file=sys.stderr)
            return True
        return False

    def check(self, signing: bool) -> None:
        """Before the builds: its owner can write to it, and a signed database needs signed packages."""
        if not os.access(self.root, os.W_OK):
            owner = self.root.owner()
            raise BuildError(
                f"Can't write to {self.root} (the repository {self.name}): run as its owner, {owner}"
            )
        if not signing and self.signed():
            raise BuildError(
                f"The database of {self.name} is signed, the packages need signing too (without --no-sign)"
            )

    def add(self, files: Sequence[Path], signing: bool) -> None:
        """Add package files, signed like the database (as aur build --sign does).

        Not over a newer version (--prevent-downgrade), e.g. of an AUR dependency aur sync has updated
        there since. Not pacman's copy of the database, as aur build --chroot doesn't: pacman -Syu
        syncs it, without a sudo rule for pacsync.
        """
        self.check(signing)
        added = []
        for file in files:
            target = self.root / file.name
            shutil.copyfile(file, target)
            if signing:
                key = ["-u", os.environ["GPGKEY"]] if os.environ.get("GPGKEY") else []
                subprocess.run(
                    [
                        "gpg",
                        "--detach-sign",
                        "--no-armor",
                        "--batch",
                        "--yes",
                        *key,
                        "--output",
                        f"{target}.sig",
                        "--",
                        str(target),
                    ],
                    check=True,
                )
            else:
                # One of an earlier build of the same file wouldn't match it
                Path(f"{target}.sig").unlink(missing_ok=True)
            added.append(str(target))
        command = [
            "repo-add",
            "--wait-for-lock",
            "--prevent-downgrade",
            *(["--sign"] if signing else []),
            "--",
            str(self.db),
            *added,
        ]
        subprocess.run(command, cwd=self.root, env={**os.environ, "LANG": "C"}, check=True)
        print(
            f"Added {len(added)} files to {self.name} ({self.root}), pacman -Syu installs them",
            file=sys.stderr,
        )


def makepkg_signs() -> bool:
    """Whether makepkg signs: sign in BUILDENV, from its configuration as makepkg loads it."""
    script = 'set +u; source /usr/share/makepkg/util.sh; load_makepkg_config; [[ " ${BUILDENV[*]} " == *" sign "* ]]'
    return subprocess.run(["bash", "-c", script], capture_output=True, check=False).returncode == 0


def uses_testing() -> bool:
    """Whether pacman.conf enables Arch Linux's testing repositories."""
    repos = subprocess.run(
        ["pacman-conf", "--repo-list"], capture_output=True, text=True, check=True
    ).stdout.split()
    return any(re.fullmatch(r"(core|extra|multilib)-testing", repo) for repo in repos)


@dataclass
class Build:
    """The settings of a build, from its options."""

    method: str = "chroot"
    install: bool = False
    dry_run: bool = False
    keep: bool = False
    add: bool = False
    signing: bool | None = None
    dotnet_bin: bool = False
    nuget_bin: bool = False
    testing: bool = False
    sanitise: str = ""
    target: str = ""
    reuse: str = ""
    fetch_keys: bool = False
    # Dependencies from the system's aurutils repository: None for the default, with --add
    system_repo: bool | None = None
    system: tuple[str, Path] | None = None
    targets: list[str] = field(default_factory=list)
    alias: dict[str, str] = field(default_factory=dict)
    preinstall: list[str] = field(default_factory=list)


def cross_ready(package: Path) -> bool:
    """Whether a cross build can build a package for aarch64: the cross makepkg.conf only sets CARCH,
    so a PKGBUILD that compiles has to build for it itself, else its compilers build for x86_64,
    without an error. Ready: one that builds nothing (prebuilt sources, a selector), one that follows
    $CARCH (a .NET RID, Node's architecture) or compiles for the Arch Linux ARM root ($ROOTFS_DIR),
    and one with sources or other arrays of its own for aarch64. cross_built checks the result."""
    if "aarch64" not in architectures(package):
        return True
    pkgbuild = (package / "PKGBUILD").read_text()
    return (
        not re.search(r"^build\(\)", pkgbuild, re.MULTILINE)
        or re.search(r"\$\{?(CARCH|ROOTFS_DIR)\b", pkgbuild) is not None
        or re.search(r"^\w+_aarch64=", pkgbuild, re.MULTILINE) is not None
    )


# The machine of an ELF file (e_machine), for the architectures a cross build could put into a package
ELF_MACHINES = {3: "i386", 62: "x86_64", 183: "aarch64"}


def cross_built(package_file: Path) -> list[str]:
    """The files of a package cross-built for aarch64 that are ELF files for x86, which cross_ready
    let through: a PKGBUILD that compiles for the build host after all."""
    wrong = []
    with tarfile.open(package_file) as archive:
        for member in archive:
            if not member.isfile() or member.size < 20:
                continue
            content = archive.extractfile(member)
            header = content.read(20) if content else b""
            if header[:4] != b"\x7fELF":
                continue
            # e_machine: 2 bytes at offset 18, in the file's byte order (EI_DATA, 1: little endian)
            machine = int.from_bytes(header[18:20], "little" if header[5] == 1 else "big")
            if ELF_MACHINES.get(machine) in ("i386", "x86_64"):
                wrong.append(f"{member.name} ({ELF_MACHINES[machine]})")
    return wrong


def check_cross_built(folder: Path, cross_repo: Path) -> None:
    """Fail when a package cross-built for aarch64 has programs or libraries for x86."""
    srcinfo = Srcinfo.load(folder)
    for name in srcinfo.packages:
        for package_file in cross_repo.glob(f"{name}-{srcinfo.version()}-aarch64.pkg.tar.*"):
            if package_file.name.endswith(".sig"):
                continue
            if wrong := cross_built(package_file):
                raise BuildError(
                    f"{package_file.name} was cross-built with files for x86, so its PKGBUILD doesn't "
                    f"build for aarch64 itself: {', '.join(wrong[:5])}. Build it with --target "
                    "aarch64-native instead"
                )


def architectures(package: Path) -> list[str]:
    """The architectures of a package, of its pkgbase and its packages."""
    return [value for key, value in srcinfo_lines(package) if key == "arch"]


def builds_for(package: Path, carch: str) -> bool:
    """Whether a package builds for a CARCH: it's in its arch, or the package is for any."""
    arches = architectures(package)
    return carch in arches or "any" in arches


def needs_dotnet(package: Path) -> bool:
    """Whether a package builds or runs with .NET: it depends on a dotnet-* package (the SDK, a
    runtime, a dotnet-build-deps selector)."""
    return any(
        DEPENDS.match(key) and bare(value).startswith("dotnet-") for key, value in srcinfo_lines(package)
    )


def roots(checkout: Checkout, names: Sequence[str]) -> list[str]:
    """Each argument a template, expanded to its root packages, or a package."""
    result: list[str] = []
    for name in names:
        name = name.rstrip("/")
        if name in BUILD_TEMPLATES:
            result += BUILD_TEMPLATES[name]
        elif folder := checkout.package_dir(name):
            result.append(folder)
        else:
            raise SelectionError(f"Not a template or package: {name}")
    return result


def validate(build: Build) -> SystemRepo | None:
    """The combinations of options a build can't do, and what --add and --target imply; the system's
    repository for --add."""
    if build.target and build.target not in TARGETS:
        raise BuildError(
            f"Unknown target: {build.target} ("
            + ", ".join(f"{name} {what}" for name, (_, what) in TARGETS.items())
            + ")"
        )
    if build.method == "local" and (
        build.dotnet_bin or build.nuget_bin or build.testing or build.target or build.reuse
    ):
        raise BuildError(
            "--dotnet-bin, --nuget-bin, --testing, --target and --repo need a chroot build, a local one uses what's installed"
        )
    tools = [("makepkg", "pacman")]
    if build.method == "chroot":
        tools += [("aur", "aurutils"), ("makechrootpkg", "devtools"), ("arch-nspawn", "devtools")]
    if build.add:
        tools += [("aur", "aurutils"), ("repo-add", "pacman"), ("gpg", "gnupg")]
    if build.target:
        # And the command that runs the setup of the target's root as root
        command = auth()[0]
        tools += [("curl", "curl"), ("gpg", "gnupg"), (command, AUTH_PACKAGES.get(command, command))]
    require("build", tools)
    # Programs for aarch64 run in the Arch Linux ARM root under QEMU, registered with binfmt_misc
    if build.target.startswith("aarch64") and not Path("/proc/sys/fs/binfmt_misc/qemu-aarch64").exists():
        raise BuildError(
            "--target needs QEMU for aarch64 programs: qemu-user-static-binfmt, then systemctl restart systemd-binfmt"
        )
    if build.sanitise:
        for sanitiser in build.sanitise.split(","):
            if sanitiser not in ("address", "undefined"):
                raise BuildError(
                    f"Unknown sanitiser: {sanitiser} (address, undefined or both, comma-separated)"
                )
        if build.method == "local" or build.target:
            raise BuildError("--sanitize needs a chroot build for x86_64")
        # The test builds are no use without their packages
        build.keep = True
    if build.signing is not None and not build.add:
        raise BuildError("--sign and --no-sign are for the packages --add adds")
    system: SystemRepo | None = None
    if build.add:
        if build.method == "local" or build.sanitise or build.target:
            raise BuildError(
                "--add needs a chroot build for x86_64, without --sanitize (test builds aren't to be installed)"
            )
        system = SystemRepo.find()
        build.signing = system.signing(build.signing)
        if not build.dry_run:
            system.check(build.signing)
        # Against the repositories the system uses: a package built against stable can depend on a
        # library soname testing has replaced
        if uses_testing():
            if not build.testing:
                print(
                    "The system uses the testing repositories, building against them (--testing)",
                    file=sys.stderr,
                )
                build.testing = True
        elif build.testing:
            raise BuildError(
                "--testing builds against the testing repositories, which the system doesn't use"
            )
    if build.testing and build.target:
        raise BuildError("--testing is for Arch Linux's testing repositories, not those of its ports")
    if build.target and os.uname().machine != "x86_64":
        raise BuildError(f"--target is for x86_64 hosts, build natively on {os.uname().machine}")
    if build.target == "aarch64-native" and not build.dotnet_bin:
        print(
            "Arch Linux ARM has no .NET, --target aarch64-native builds with Microsoft's (--dotnet-bin)",
            file=sys.stderr,
        )
        build.dotnet_bin = True
    if build.target == "i686" and (build.dotnet_bin or build.nuget_bin):
        raise BuildError("--dotnet-bin and --nuget-bin are for .NET, which has no build for i686")
    return system


def selectors(checkout: Checkout, build: Build) -> None:
    """The -bin selectors, aliased for the source-built ones, and preinstalled into each chroot
    (makechrootpkg -I) once built.

    So pacman doesn't resolve the names the packages depend on to Arch's .NET or the source-built
    selectors in another repository: a selector depends on Microsoft's packages by their own names,
    which aur sync built into the private repository, and those provide the names of Arch's.
    --dotnet-bin: one per .NET version with a source-built selector (not dotnet-build-deps-11.0-bin,
    the only provider of its .NET anyway); --nuget-bin: the packages of the split
    powershell-build-deps-bin.
    """
    if build.dotnet_bin:
        for selector in sorted(p.name for p in checkout.root.glob("dotnet-build-deps-*-bin")):
            if not (checkout.root / selector.removesuffix("-bin")).is_dir():
                continue
            build.alias[selector.removesuffix("-bin")] = selector
            build.preinstall.append(selector)
    if build.nuget_bin:
        names = list(Srcinfo.load(checkout.root / "powershell-build-deps-bin").packages)
        for name in names:
            build.alias[name.removesuffix("-bin")] = "powershell-build-deps-bin"
        build.preinstall += list(names)


def run(command: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode:
        raise BuildError("", result.returncode)


def run_build(checkout: Checkout, names: Sequence[str], build: Build) -> int:
    """Build packages or templates and their dependencies in order: see the module's docstring."""
    if not names:
        print("aur-packages build: expected templates or packages (aur-packages help build)", file=sys.stderr)
        return 2
    # The private repository's files, the packages, and the copies --add puts into the system's
    # repository are read by pacman's DownloadUser (alpm), whatever the user's umask (027 for a
    # dedicated aurutils user, say)
    os.umask(0o022)
    try:
        return build_all(checkout, names, build)
    except BuildError as error:
        if str(error):
            print(error, file=sys.stderr)
        return error.code
    except subprocess.CalledProcessError as error:
        return error.returncode
    except keys.MissingKeys as error:
        print(error, file=sys.stderr)
        return 1


def build_all(checkout: Checkout, names: Sequence[str], build: Build) -> int:
    system = validate(build)
    # A native build runs everything in the root of the target's port (Arch Linux ARM under QEMU,
    # Arch Linux 32), a cross build compiles against Arch Linux ARM's
    native, cross = build.target in ("aarch64-native", "i686"), build.target == "aarch64"
    carch = TARGETS[build.target][0] if build.target else "x86_64"
    # The containers, apart from aurutils' own (/var/lib/aurbuild); testing ones of their own, as a
    # chroot upgraded to the testing repositories can't go back
    base = Path(os.environ.get("AUR_BUILD_CHROOT", "/var/lib/aur-packages-chroot"))
    suffix = "-testing" if build.testing else ""
    devtools_conf, multilib_conf = f"extra{suffix}.conf", f"multilib{suffix}.conf"
    chroot_dir, multilib_dir = base / f"x86_64{suffix}", base / f"multilib-x86_64{suffix}"
    alarm, cross_dir = base / "aarch64", base / "x86_64-cross-aarch64"
    native_dir = base / "i686" if build.target == "i686" else alarm
    selectors(checkout, build)

    graph = edges(checkout, build.alias)
    build.targets = roots(checkout, names)
    packages = order(checkout, build.targets, graph)
    if not packages:
        raise BuildError("Nothing to build")
    if cross and (unprepared := [p for p in packages if not cross_ready(checkout.root / p)]):
        raise BuildError(
            "--target aarch64 cross-builds only PKGBUILDs that build for aarch64 themselves ($CARCH, "
            f"$ROOTFS_DIR), unlike these: {', '.join(unprepared)}. Their aarch64 packages would have "
            "x86_64 programs: build them natively under QEMU with --target aarch64-native instead"
        )
    if build.target == "i686" and (
        dotnet := [
            p for p in packages if builds_for(checkout.root / p, carch) and needs_dotnet(checkout.root / p)
        ]
    ):
        raise BuildError(
            "--target i686 can't build packages with .NET, which neither Arch Linux 32 nor Microsoft "
            f"builds for 32-bit x86: {', '.join(dotnet)}"
        )
    # The dependencies the system's aurutils repository has in their current version come from there
    # (--system-repo), by default for its own packages (--add, sysupgrade)
    if build.system_repo and (build.method == "local" or build.target):
        raise BuildError("--system-repo needs a chroot build for x86_64")
    if build.system_repo is None:
        build.system_repo = build.add
    if build.system_repo:
        repository = system or SystemRepo.find()
        build.system = (repository.name, repository.root)

    # The private repository: each build resolves the packages built before it from there
    makepkg_conf = MAKEPKG_CONF
    repo = Path("<repo>")
    temporary = False
    if build.method == "chroot" and build.dry_run:
        repo = Path(build.reuse) if build.reuse else Path("<repo>")
    elif build.method == "chroot":
        if build.target == "i686":
            archlinux32_root(native_dir)
        elif native or cross:
            alarm_root(alarm)
        if build.reuse:
            repo = (checkout.cwd / build.reuse).resolve()
            build.keep = True
            if not (repo / "pacman.conf").is_file():
                raise BuildError(f"{repo} isn't a repository of ./aur-packages build --keep")
        else:
            repo = Path(tempfile.mkdtemp(prefix="aur-build.", dir=os.environ.get("TMPDIR", "/tmp")))
            temporary = not build.keep
            # Readable by pacman's download user in the chroot (DownloadUser = alpm)
            repo.chmod(0o755)
            if build.target == "i686":
                conf_text = archlinux32_pacman_conf(native_dir, (REPO_NAME, repo))
            elif native:
                conf_text = alarm_pacman_conf(alarm, (REPO_NAME, repo))
            else:
                conf_text = devtools_pacman_conf(devtools_conf, repo, build.system)
            (repo / "pacman.conf").write_text(conf_text)
            empty_database(repo, REPO_NAME)
    status = 1
    try:
        status = build_packages(checkout, build, packages, graph, repo, makepkg_conf, system,
                                chroot_dir, multilib_dir, alarm, cross_dir, multilib_conf, native, cross,
                                native_dir, carch)  # fmt: skip
        return status
    finally:
        # A failed build keeps what it built, to continue where it stopped
        if temporary and status and package_files(repo):
            print(
                f"Kept the repository of the packages built so far, {repo}: continue where the build "
                f"stopped with --repo {repo}",
                file=sys.stderr,
            )
        elif temporary:
            shutil.rmtree(repo, ignore_errors=True)


def build_packages(
    checkout: Checkout, build: Build, packages: list[str], graph: set[tuple[str, str]], repo: Path,
    makepkg_conf: Path, system: SystemRepo | None, chroot_dir: Path, multilib_dir: Path,
    alarm: Path, cross_dir: Path, multilib_conf: str, native: bool, cross: bool,
    native_dir: Path, carch: str,
) -> int:  # fmt: skip
    root, dry = checkout.root, build.dry_run
    conf = repo / "pacman.conf"
    chroot_args: list[str] = []
    # A native build runs everything in the root of the target's port: Arch Linux ARM under QEMU,
    # Arch Linux 32 as it is
    if native:
        chroot_dir = native_dir
        makepkg_conf = repo / f"makepkg-{carch}.conf"
        if not dry and carch == "aarch64":
            makepkg_conf.write_text(alarm_makepkg_conf(alarm))
        elif not dry:
            makepkg_conf.write_text(
                archlinux32_makepkg_conf((native_dir / "root" / "etc" / "makepkg.conf").read_text())
            )
        chroot_args += ["--makepkg-conf", str(makepkg_conf)]
    chroot_args += ["--directory", str(chroot_dir)]
    # Test builds with the sanitisers take their flags from a makepkg.conf of their own
    sanitise_args: list[str] = []
    if build.sanitise:
        sanitise_conf = repo / "makepkg-sanitise.conf"
        sanitise_args = ["--makepkg-conf", str(sanitise_conf)]
        if not dry:
            sanitise_conf.write_text(sanitise_makepkg_conf(makepkg_conf, build.sanitise))
        chroot_args += sanitise_args
    # A cross build builds everything for x86_64, those for aarch64 as well afterwards, in a container
    # of their own with the cross toolchain and the Arch Linux ARM root, into a repository of their own
    cross_repo, cross_conf, cross_makepkg = (
        repo / "aarch64",
        repo / "pacman-cross-aarch64.conf",
        repo / "makepkg-cross-aarch64.conf",
    )
    cross_args = [
        "--directory", str(cross_dir), "--makepkg-conf", str(cross_makepkg), "--bind", str(alarm / "root"),
        "--base-packages", "base-devel,clang,lld,aarch64-linux-gnu-binutils,rust-aarch64-gnu",
    ]  # fmt: skip
    if cross and not dry:
        cross_repo.mkdir(exist_ok=True)
        cross_repo.chmod(0o755)
        if not (cross_repo / f"{CROSS_NAME}.db.tar.gz").exists():
            empty_database(cross_repo, CROSS_NAME)
        cross_conf.write_text(
            conf.read_text() + f"\n[{CROSS_NAME}]\nSigLevel = Never\nServer = file://{cross_repo}\n"
        )
        cross_makepkg.write_text(cross_makepkg_conf(alarm))

    # Dependencies only the AUR has, built by aurutils into the private repository first (with their
    # own AUR dependencies): e.g. lasso for sogo, or Microsoft's .NET of a -bin selector. Names that
    # aren't packages in the AUR are provides of the ones built, e.g. dotnet-runtime-11.0.
    if build.method == "chroot":
        aur_deps = aur_only_deps(checkout, DEVTOOLS / "pacman.conf.d" / multilib_conf, packages)
        aur_names: list[str] = []
        if aur_deps:
            info = subprocess.run(
                ["aur", "query", "-t", "info", *aur_deps], capture_output=True, text=True, check=True
            )
            aur_names = sorted(r["Name"] for r in json.loads(info.stdout).get("results", []))
        if not dry:
            # Verified with the keyring of aur sync -K, which aur build passes to makepkg in the chroot
            home = keys.keyring()
            os.environ["AUR_MAKEPKG_GNUPGHOME"] = str(home)
            keys.prepare([root / p for p in packages] + keys.aur_queue(aur_names), home, build.fetch_keys)
        for name in aur_names:
            command = ["aur", "sync", "--chroot", "--no-sync", "--database", REPO_NAME, "--root", str(repo),
                       "--pacman-conf", str(conf), *chroot_args, "--no-view", "--noconfirm", name]  # fmt: skip
            if dry and build.system and package_files(build.system[1], name):
                print(f"# {name}: in {build.system[0]} already", file=sys.stderr)
            elif dry:
                print(" ".join(command))
            elif package_files(repo, name):
                print(f">>> {name} is in {repo} already", file=sys.stderr)
            elif build.system and package_files(build.system[1], name):
                print(f">>> {name} is in {build.system[0]} already", file=sys.stderr)
            else:
                print(f">>> Building {name} (aur sync)", file=sys.stderr)
                # 22: the dependencies have a cycle, which checkdepends can make (python-celery's on
                # python-pytest-celery, which depends on it): built without check(), as aur sync suggests
                code = subprocess.run(command, check=False).returncode
                if code == 22:
                    print(
                        f">>> {name}: its dependencies have a cycle, building them without check()",
                        file=sys.stderr,
                    )
                    run([*command, "--no-check"])
                elif code:
                    raise BuildError("", code)
        for name in aur_deps:
            if name in aur_names:
                continue
            if dry:
                print(f"# {name}: provided by the AUR packages above", file=sys.stderr)
            elif not repo_provides(repo, name) and not (
                build.system and repo_provides(build.system[1], name)
            ):
                raise BuildError(
                    f"aur-packages: {name} is neither in the repositories, nor a package of this repository or the AUR, nor provided by one"
                )
    if build.method == "local" and not dry:
        # makepkg with the builder's own configuration and keyring, only checked
        keys.prepare([root / p for p in packages], None, fetch=False)
    # The packages of this repository built so far, or taken from the system's repository, by the
    # names of their packages
    built: set[str] = set()

    for package in packages:
        folder = root / package
        arches = architectures(folder)
        if native and not builds_for(folder, carch):
            print(f">>> Skipping {package}, it isn't for {carch}", file=sys.stderr)
            continue
        files: list[str] = []
        if build.method == "chroot":
            package_conf, package_args = conf, chroot_args
            # A package against multilib builds in a multilib container, with the same repository
            if not native and multilib(checkout, package, graph):
                package_conf = repo / "pacman-multilib.conf"
                package_args = [
                    "--directory",
                    str(multilib_dir),
                    "--base-packages",
                    "base-devel,multilib-devel",
                    *sanitise_args,
                ]
                if not dry and not package_conf.exists():
                    package_conf.write_text(devtools_pacman_conf(multilib_conf, repo, build.system))
            command = ["aur", "build", "--chroot", "--no-sync", "--database", REPO_NAME, "--root", str(repo),
                       "--pacman-conf", str(package_conf), *package_args, "--force"]  # fmt: skip
            # The packages to preinstall that are built by now
            preinstalled = []
            for name in build.preinstall:
                if name not in built:
                    continue
                if dry:
                    preinstalled.append(f"{repo}/{name}-<version>.pkg.tar<compression>")
                else:
                    found = package_files(repo, name)
                    if not found and build.system:
                        found = package_files(build.system[1], name)
                    preinstalled += [str(file) for file in found]
            if preinstalled:
                files = ["--cargs=" + ",".join(f"-I,{p}" for p in preinstalled)]
            command += files
        else:
            command = [
                "makepkg",
                "--force",
                "--cleanbuild",
                "--nodeps",
                *(["--install"] if build.install else []),
            ]
        in_system = (
            build.system is not None
            and package not in build.targets
            and built_already(folder, build.system[1], makepkg_conf)
        )
        if in_system and build.system:
            print(f">>> {package} is in {build.system[0]} already", file=sys.stderr)
        elif dry:
            print(f"(cd {package} && {' '.join(command)})")
        elif build.reuse and built_already(folder, repo, makepkg_conf):
            print(f">>> {package} is in {repo} already", file=sys.stderr)
        else:
            print(f">>> Building {package}", file=sys.stderr)
            run(command, cwd=folder)
        # By the names of its packages, which the packages to preinstall are looked up by
        built.update(Srcinfo.load(folder).packages)

        if cross and "aarch64" in arches:
            command = ["aur", "build", "--chroot", "--no-sync", "--database", CROSS_NAME, "--root", str(cross_repo),
                       "--pacman-conf", str(cross_conf), *cross_args, "--force", *files]  # fmt: skip
            if dry:
                print(f"(cd {package} && {' '.join(command)})")
            elif build.reuse and built_already(folder, cross_repo, cross_makepkg):
                print(f">>> {package} for aarch64 is in {cross_repo} already", file=sys.stderr)
            else:
                print(f">>> Building {package} for aarch64", file=sys.stderr)
                run(command, cwd=folder)
                check_cross_built(folder, cross_repo)

    if system is not None:
        if dry:
            print(
                f"# then add the packages of {repo} to the system's aurutils repository"
                + (", signed" if build.signing else ""),
                file=sys.stderr,
            )
        else:
            # Only once all have been built, so a failed build leaves the repository as it was
            system.add(package_files(repo), bool(build.signing))
    if build.method == "chroot" and build.keep and not dry:
        print(f"Repository kept at {repo}", file=sys.stderr)
        if build.sanitise:
            print(
                f"Its packages are test builds with -fsanitize={build.sanitise}, not to be installed as the usual ones",
                file=sys.stderr,
            )
        if cross:
            print(f"The aarch64 packages are in {cross_repo}", file=sys.stderr)
    return 0


def newer(version: str, than: str) -> bool:
    """Whether a version is newer than another, by pacman's comparison."""
    return (
        int(subprocess.run(["vercmp", version, than], capture_output=True, text=True, check=True).stdout) > 0
    )


def upgrades(
    checkout: Checkout, in_repo: dict[str, str], installed: dict[str, str]
) -> tuple[list[str], list[str]]:
    """The folders sysupgrade builds, and the names of all our packages, which aur sync leaves out.

    Ours with a newer version here than the aurutils repository has; and an override (overrides/)
    with a newer version than the installed package it replaces, which isn't in the repository yet:
    it's there to replace Arch Linux's package, which sysupgrade would never build otherwise.
    """
    selected, ignore = [], []
    for folder in checkout.package_dirs():
        srcinfo = Srcinfo.load(checkout.root / folder)
        names = list(srcinfo.packages)  # every pkgname, also one named -debug
        ignore += names
        version = srcinfo.version()
        for name in names:
            if name in in_repo:
                current, where = in_repo[name], "repository"
            elif folder.startswith("overrides/") and name in installed:
                current, where = installed[name], "installed"
            else:
                continue
            if newer(version, current):
                print(f"{folder}: {current} ({where}) -> {version}", file=sys.stderr)
                selected.append(folder)
                break
    return selected, ignore


def run_sysupgrade(
    checkout: Checkout, sign: bool | None, sync_options: Sequence[str], settings: Build | None = None
) -> int:
    """aur sync -u with our packages first.

    Ours (top level, local/, overrides/) that are in the aurutils repository with a newer version here,
    and overrides newer than the installed package they replace, are built and added (build --add),
    then aur sync -u updates the rest, leaving all of ours out, which it would replace with the AUR's;
    both sign as build --add decides.
    """
    require("sysupgrade", [("aur", "aurutils")])
    system = SystemRepo.find()
    signing = system.signing(sign)
    listed = subprocess.run(
        ["aur", "repo", "--database", system.name, "--list"], capture_output=True, text=True, check=True
    ).stdout
    in_repo = dict(line.split("\t", 1) for line in listed.splitlines() if "\t" in line)
    installed = dict(
        line.split(" ", 1)
        for line in subprocess.run(
            ["pacman", "-Q"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        if " " in line
    )
    selected, ignore = upgrades(checkout, in_repo, installed)
    if selected:
        settings = settings or Build()
        settings.add, settings.signing = True, signing
        status = run_build(checkout, selected, settings)
        if status:
            return status
    else:
        print(f"Our packages in {system.name} are up to date", file=sys.stderr)
    command = ["aur", "sync", "--database", system.name, "--upgrades", "--ignore", ",".join(ignore)]
    if settings and settings.fetch_keys:
        command.append("--auto-key-retrieve")
    elif not {"-K", "--auto-key-retrieve", "--autokeyretrieve"} & set(sync_options):
        # Its keys before it builds anything, in the keyring of its makepkg, the builder's own
        queue = keys.aur_queue([], command[2:])
        try:
            keys.prepare(queue, None, fetch=False)
        except keys.MissingKeys as error:
            print(f"{error}\nOr run sysupgrade with -K", file=sys.stderr)
            return 1
    return subprocess.run([*command, *(["--sign"] if signing else []), *sync_options], check=False).returncode
