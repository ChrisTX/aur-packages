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
- PowerShell code goes into `.ps1`/`.psm1` files shipped as sources (annotated 0BSD in REUSE.toml), not inline `pwsh -Command '…'` blocks, so editors can support it. Pass values from the PKGBUILD as script parameters (`pwsh -NoProfile -NonInteractive -File "$srcdir/script.ps1" -Param "$value"`) instead of splicing shell variables into the code.

## Building from source

- Build dependencies from source wherever possible instead of using prebuilt binaries, especially PowerShell Gallery modules: build them from their upstream repositories (see powershell's `build-modules.ps1`/`powershell-modules.psm1`). For unmaintained or untagged modules, use the latest commit, as it may contain fixes that were never released.
- .NET packages build with the latest .NET SDK in the repositories (`dotnet-sdk`, versioned like `dotnet-sdk-10.0`), not the version upstream pins in `global.json`.
- Take .NET runtime packages from `dotnet-source-built-artifacts` instead of nuget.org where they're available, so they match the source-built .NET they run on (see powershell's `prepare()`: package source mapping in a generated `nuget.config`, `arch-x64` RID).
- Publish .NET assemblies with ReadyToRun wherever possible (`-p:PublishReadyToRun=true`).

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

- Every disabled, skipped or removed test gets a comment saying why. If it's an upstream bug, link the upstream issue (open one if there is none yet). Disable as little as possible: a single test or context rather than a whole file.
- Lint: `shellcheck PKGBUILD`, `namcap PKGBUILD`, and `namcap` on the built package.
- Clean-chroot builds: `pkgctl build`. A local `makepkg -fCd` is fine for a quick check, but may lack makedepends.
