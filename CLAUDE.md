# AUR packages

Each top-level directory is one AUR package, added via `git subtree` and published with aurpublish.

`./aur` manages them all, or the packages given: `pull` and `push` (aurpublish), `updates` and `upgrade` (`pkgctl version check` and `upgrade` with each `.nvchecker.toml`), `check` (the hooks of `.pre-commit-config.yaml`), `sync` (copies `templates/package` into the packages) and `setup` (installs the git hooks). See `./aur help`.

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
  - The SDK doesn't list `arch-x64` for crossgen2 packs, so ReadyToRun would use the `linux-x64` crossgen2 from nuget.org. Pass `-p:CustomAfterMicrosoftCommonTargets=$srcdir/crossgen2-pack.targets` (see powershell) to get the source-built one.
  - `PublishReadyToRun` only works for .NET (Core) projects. Assemblies targeting netstandard or .NET Framework, like most PowerShell modules, are compiled with crossgen2 directly against the runtime and `$PSHOME` (see powershell's `Invoke-ReadyToRunCompiler`). Skip copies of assemblies the runtime or `$PSHOME` already provide, as those aren't loaded.

## Per-package files

Besides `PKGBUILD` and `.SRCINFO`, every package has:

- `LICENSE` (0BSD, "Arch Linux Contributors") and `LICENSES/0BSD.txt` as a symlink to `../LICENSE`
- `REUSE.toml` annotating packaging files as 0BSD; patches derived from upstream are annotated with the upstream license
- `.gitignore`: the toptal `archlinuxpackages` template, plus the checkout directory for git sources (e.g. `ergo/`) and downloaded sources the template doesn't cover (e.g. `*.nupkg`)
- `.nvchecker.toml` for update checks (except VCS `-git` packages and sources without a usable upstream repo)
- `.editorconfig` and `.pre-commit-config.yaml`, copies of `templates/package` (`./aur sync`), so the package can be formatted and checked on its own. Change the template, not the copies; `./aur sync` writes the top-level configuration from it as well.

## Commits and aurpublish

- One commit per package.
- Message summary, the Arch convention rather than Conventional Commits (versions come from upstream, and each package's commits become its AUR history):
  - `upgpkg: <pkg> <ver>-<rel>` when pkgver/pkgrel changes, e.g. `upgpkg: powershell 7.6.9-22`.
  - Otherwise `<scope>: <summary>`, where the scope is the package directory, or the top-level file or directory for changes outside packages (e.g. `CLAUDE.md:`, `aur:`, `templates:`). The summary is lowercase and imperative (`add …`, `fix …`, `drop …`), without a trailing period.
- The body lists the changes. The commit-msg hook (`./aur commit-msg`) checks the summary: the scope has to exist, and the version in `upgpkg:` has to match the staged .SRCINFO.
- Regenerate .SRCINFO yourself (`makepkg --printsrcinfo > .SRCINFO`), the git hook only checks it. The hook (`./aur setup`, prek or pre-commit) runs the checks below on the staged files and replaces aurpublish's hooks, so commit normally; don't bypass it.

## Building and checking

- Every disabled, skipped or removed test gets a comment saying why. If it's an upstream bug, link the upstream issue (open one if there is none yet). Disable as little as possible: a single test or context rather than a whole file.
- Everything passes `./aur check`, which runs the hooks of `.pre-commit-config.yaml`: formatting (shfmt, ruff, Biome, tombi, rumdl, settings in `.editorconfig`), linting (shellcheck, shellharden, ruff, Biome, tombi, rumdl, systemd-lsp, PSScriptAnalyzer, editorconfig-checker), `reuse lint` and up-to-date .SRCINFO files. Formatters fix files themselves; run the check again afterwards. After `updpkgsums`, which aligns the checksums its own way, run shfmt on the PKGBUILD (`./aur upgrade` does).
- termux-language-server only runs on request (`./aur check --manual`): it crashes on apostrophes in optdepends (neomutt/lsp-tree-sitter#9) and has false positives.
- Also lint with `namcap PKGBUILD` and `namcap` on the built package.
- Where an unquoted variable relies on word splitting, e.g. to add nothing when it's empty, use an array instead of disabling shellharden.
- PowerShell scripts (`.ps1`/`.psm1`) are PSScriptAnalyzer-clean with its default rules, information level included (`Invoke-ScriptAnalyzer -Path script.ps1`). Suppress a rule only where the code can't comply, with `[Diagnostics.CodeAnalysis.SuppressMessageAttribute('Rule', '', Justification = '…')]` saying why.
- Clean-chroot builds: `pkgctl build`. A local `makepkg -fCd` is fine for a quick check, but may lack makedepends.
