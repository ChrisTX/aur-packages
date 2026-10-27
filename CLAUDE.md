# AUR packages

Each top-level directory is one AUR package, added via `git subtree` and published with aurpublish.

## PKGBUILD conventions

- Maintainer line: `# Maintainer: Christian Pfeiffer <cpfeiffer at rev-crew dot info>`
- Right after the Maintainer/Contributor lines, every PKGBUILD has exactly this header, so `shellcheck PKGBUILD` works without extra options:

  ```bash
  # shellcheck disable=SC2034,SC2154
  # shellcheck shell=bash
  ```

- Never disable SC2164. Write `cd … || exit` instead, even where makepkg's errexit makes it redundant.
- Checksums: always both `sha512sums` and `b2sums` (per-arch variants too), never sha256-only or b2-only. Before running `updpkgsums`, seed both arrays (e.g. `'SKIP'`); with empty arrays it falls back to sha256.
- Bump pkgrel when the built package changes (files, depends, license, other metadata). Style-only or packaging-only changes don't get a bump.
- Go packages keep `GOPATH` inside `$srcdir`.

## Per-package files

Besides `PKGBUILD` and `.SRCINFO`, every package has:

- `LICENSE` (0BSD, "Arch Linux Contributors") and `LICENSES/0BSD.txt` as a symlink to `../LICENSE`
- `REUSE.toml` annotating packaging files as 0BSD; patches derived from upstream are annotated with the upstream license
- `.gitignore`: the toptal `archlinuxpackages` template, plus the checkout directory for git sources (e.g. `ergo/`)
- `.nvchecker.toml` for update checks (except VCS `-git` packages and sources without a usable upstream repo)

## Commits and aurpublish

- One commit per package.
- Message: `upgpkg: <pkg> <ver>-<rel>` when pkgver/pkgrel changes, otherwise `<pkg>: <summary>`. The body lists the changes.
- aurpublish's git hooks mainly regenerate .SRCINFO, and `prepare-commit-msg` prepends "upgpkg: … / upstream release" to every message. When you've regenerated .SRCINFO yourself (`makepkg --printsrcinfo > .SRCINFO`), commit with `git -c core.hooksPath=/dev/null commit …` so the message stays as written.

## Building and checking

- Lint: `shellcheck PKGBUILD`, `namcap PKGBUILD`, and `namcap` on the built package.
- Clean-chroot builds: `pkgctl build`. A local `makepkg -fCd` is fine for a quick check, but may lack makedepends.
