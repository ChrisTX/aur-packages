# Contributing

Thanks for helping with these packages. Each top-level directory is one AUR package, added via `git subtree` and published with aurpublish: this repository is where the packages are developed, the AUR is where they're published. Pull requests here are welcome; the maintainer publishes merged changes to the AUR, each package's commits becoming its AUR history.

For problems with a package, open an issue here or comment on its AUR page. Problems of the software itself belong upstream, the `url` of the PKGBUILD.

## Getting started

The tools of the checks are all in the Arch Linux repositories, apart from PSScriptAnalyzer, which comes with `powershell-editor-services` (this repository, or the AUR):

```bash
sudo pacman -S --needed base-devel devtools pacman-contrib namcap nvchecker jq \
  prek shfmt shellcheck shellharden ruff biome tombi rumdl systemd-lsp \
  editorconfig-checker reuse
```

`./aur-packages build` also needs aurutils, and the aarch64 builds `qemu-user-static-binfmt`; publishing to the AUR (`./aur-packages pull` and `push`) needs aurpublish. Then install the git hooks, which run the checks on the staged files before each commit and check the commit message:

```bash
./aur-packages setup
```

`./aur-packages` manages all packages, or the packages given: `pull` and `push` (aurpublish), `updates` and `upgrade` (`pkgctl version check` and `upgrade` with each `.nvchecker.toml`), `check` (the hooks of `.pre-commit-config.yaml`), `build` (clean-chroot builds of packages and their dependencies from this repository, with aurutils), `sync` (copies `templates/package` into the packages), `setup` (installs the git hooks) and `list` (the packages). See `./aur-packages help`.

### `aur-packages` in your shell

To use it from anywhere, put it on PATH:

```bash
ln -s "$PWD/aur-packages" ~/.local/bin/aur-packages
```

Run from PATH, it works on the checkout of the current directory, so worktrees and other clones just work; elsewhere on the checkout `AUR_PACKAGES_HOME` names, or without it on the one the symlink points into (a copy instead of a symlink needs `AUR_PACKAGES_HOME`). It always runs that checkout's own `aur-packages`, and `./aur-packages` in a checkout always works on that one.

```bash
export AUR_PACKAGES_HOME=~/Projects/AUR
```

The completions cover `aur-packages` and `./aur-packages`, with the commands, their options and the packages. Load them in your shell's configuration:

| Shell | Configuration | Line |
| --- | --- | --- |
| bash | `~/.bashrc` | `source <(aur-packages completion bash)` |
| zsh | `~/.zshrc`, after `compinit` | `source <(aur-packages completion zsh)` |
| fish | `~/.config/fish/config.fish` | `aur-packages completion fish \| source` |
| PowerShell | `$PROFILE` | `aur-packages completion pwsh \| Out-String \| Invoke-Expression` |

Or save them where the shell loads completions from: `aur-packages completion zsh > _aur-packages` in a folder of `$fpath`, `aur-packages completion fish > ~/.config/fish/completions/aur-packages.fish`.

A typical change:

1. Edit the PKGBUILD (and its sources), then regenerate `.SRCINFO` with `makepkg --printsrcinfo > .SRCINFO`.
2. Build it in a clean chroot: `./aur-packages build <package>` builds it with its dependencies from this repository, `pkgctl build` works for a single package.
3. Run `./aur-packages check <package>` and `namcap` on the PKGBUILD and the built package.
4. Commit each package on its own, with a message as described in [Commits](#commits-and-aurpublish).

The conventions below apply to every package. GitHub Actions runs `./aur-packages check` on every push and pull request.

## PKGBUILD conventions

- Maintainer line: `# Maintainer: Christian Pfeiffer <cpfeiffer at rev-crew dot info>`
- Right after the Maintainer/Contributor lines, every PKGBUILD has exactly this header, so `shellcheck PKGBUILD` works without extra options:

  ```bash
  # shellcheck disable=SC2034,SC2154
  # shellcheck shell=bash
  ```

- Never disable SC2164. Write `cd … || exit` instead, even where makepkg's errexit makes it redundant.
- Quoting in the metadata arrays (`arch`, `license`, `depends`, `optdepends`, `options`, `backup`, …): plain words stay bare (`arch=(x86_64 aarch64)`, `options=(!debug)`), literal text that needs quotes gets single quotes (`'powershell>=7.6.9-3'`, `'git: for git sources'`), double quotes only where something expands or the text has an apostrophe (`"dotnet-runtime-$_dotnetsdkver"`), around the whole word. Scalars like `pkgdesc` and `url` are left as they are. The quoting hook checks it (`./aur-packages quoting`).
- Checksums: always both `sha512sums` and `b2sums` (per-arch variants too), never sha256-only or b2-only. Before running `updpkgsums`, seed both arrays (e.g. `'SKIP'`); with empty arrays it falls back to sha256.
- Bump pkgrel when the built package changes (files, depends, license, other metadata). Style-only or packaging-only changes don't get a bump.
- Go packages keep `GOPATH` inside `$srcdir`.
- PowerShell code goes into `.ps1`/`.psm1` files shipped as sources (annotated 0BSD in REUSE.toml), not inline `pwsh -Command '…'` blocks, so editors can support it. Pass values from the PKGBUILD as script parameters (`pwsh -NoProfile -NonInteractive -File "$srcdir/script.ps1" -Param "$value"`) instead of splicing shell variables into the code.

## Building from source

- Build dependencies from source wherever possible instead of using prebuilt binaries, especially PowerShell Gallery modules: build them from their upstream repositories (see powershell's `build-modules.ps1`/`powershell-modules.psm1`). For unmaintained or untagged modules, use the latest commit, as it may contain fixes that were never released.
- .NET packages build with the latest .NET SDK in the repositories (`dotnet-sdk`, versioned like `dotnet-sdk-10.0`), not the version upstream pins in `global.json`.
- Take .NET runtime packages from `dotnet-source-built-artifacts` instead of nuget.org where they're available, so they match the source-built .NET they run on (see powershell's `prepare()`: package source mapping in a generated `nuget.config`, `arch-x64` RID).
- Two selector packages decide where the build dependencies come from, and .NET packages makedepend on them rather than on what they choose:
  - `dotnet-build-deps-10.0` (one per .NET version, like the SDK the packages build with): .NET itself, the source-built one of Arch with its artifacts, the reference packages and IO.Ports' native package, pinned to the exact release of the SDK. `dotnet-build-deps-10.0-bin` picks Microsoft's `dotnet-sdk-bin` and nuget.org instead, pinned to its exact release the same way. Both are versioned like their SDK (`10.0.14.sdk114`: runtime, feature band and patch). They conflict with each other's packages, so two builds of .NET (different feature bands and versions) never mix.
  - `powershell-build-deps` and `powershell-editor-services-build-deps`: our source-built libraries for powershell and PSES, separate packages so that building powershell alone doesn't build PSES's (makepkg installs the depends of all packages of a split PKGBUILD). `powershell-build-deps-bin` is split into a -bin package for each and ships nothing, so upstream's pins come from nuget.org.
  - NuGet packages are installed as local feeds: our libraries in `/usr/share/nuget/packages`, the packages built from the VMR's sources (the reference packages, IO.Ports' native package) in `/usr/share/nuget/dotnet-10.0/{reference-packages,packages}`, so a feed only holds packages of one build, like the source-built artifacts.
  - Consumers pick their feeds by what's installed (artifacts, our libraries in `/usr/share/nuget/packages`, the reference packages and IO.Ports' native package in `/usr/share/nuget/dotnet-10.0`), adding local feeds only when they exist (NuGet fails on missing ones). `_check_prebuilt` lets nuget.org binaries through only with the matching -bin selector installed (`pacman -T`).
- Publish .NET assemblies with ReadyToRun wherever possible (`-p:PublishReadyToRun=true`).
  - The SDK doesn't list `arch-x64` for crossgen2 packs, so ReadyToRun would use the `linux-x64` crossgen2 from nuget.org. Pass `-p:CustomAfterMicrosoftCommonTargets=$srcdir/crossgen2-pack.targets` (see powershell) to get the source-built one.
  - `PublishReadyToRun` only works for .NET (Core) projects. Assemblies targeting netstandard or .NET Framework, like most PowerShell modules, are compiled with crossgen2 directly against the runtime and `$PSHOME` (see powershell's `Invoke-ReadyToRunCompiler`). Skip copies of assemblies the runtime or `$PSHOME` already provide, as those aren't loaded.

## Per-package files

Besides `PKGBUILD` and `.SRCINFO`, every package has:

- `LICENSE` (0BSD, "Arch Linux Contributors") and `LICENSES/0BSD.txt` as a symlink to `../LICENSE`
- `REUSE.toml` annotating packaging files as 0BSD; patches derived from upstream are annotated with the upstream license
- `.gitignore`: the toptal `archlinuxpackages` template, plus the checkout directory for git sources (e.g. `ergo/`) and downloaded sources the template doesn't cover (e.g. `*.nupkg`)
- `.nvchecker.toml` for update checks (except VCS `-git` packages and sources without a usable upstream repo)
- `.editorconfig` and `.pre-commit-config.yaml`, copies of `templates/package` (`./aur-packages sync`), so the package can be formatted and checked on its own. Change the template, not the copies; `./aur-packages sync` writes the top-level configuration from it as well.

## Commits and aurpublish

- One commit per package.
- Message summary, the Arch convention rather than Conventional Commits (versions come from upstream, and each package's commits become its AUR history):
  - `upgpkg: <pkg> <ver>-<rel>` when pkgver/pkgrel changes, e.g. `upgpkg: powershell 7.6.9-22`.
  - Otherwise `<scope>: <summary>`, where the scope is the package directory, or the top-level file or directory for changes outside packages (e.g. `README.md:`, `aur-packages:`, `templates:`, `.github:`). The summary is lowercase and imperative (`add …`, `fix …`, `drop …`), without a trailing period.
- The body lists the changes. The commit-msg hook (`./aur-packages commit-msg`) checks the summary: the scope has to exist, and the version in `upgpkg:` has to match the staged .SRCINFO.
- Regenerate .SRCINFO yourself (`makepkg --printsrcinfo > .SRCINFO`), the git hook only checks it. The hook (`./aur-packages setup`, prek or pre-commit) runs the checks below on the staged files and replaces aurpublish's hooks, so commit normally; don't bypass it.

## Building and checking

- Every disabled, skipped or removed test gets a comment saying why. If it's an upstream bug, link the upstream issue (open one if there is none yet). Disable as little as possible: a single test or context rather than a whole file.
- Everything passes `./aur-packages check`, which runs the hooks of `.pre-commit-config.yaml`: formatting (shfmt, ruff, Biome, tombi, rumdl, settings in `.editorconfig`), linting (shellcheck, shellharden, ruff, Biome, tombi, rumdl, systemd-lsp, PSScriptAnalyzer, editorconfig-checker), `reuse lint`, the quoting of the metadata arrays, up-to-date .SRCINFO files and checksums of the local sources, which a formatter may have changed (run `updpkgsums` then). Formatters fix files themselves; run the check again afterwards. After `updpkgsums`, which aligns the checksums its own way, run shfmt on the PKGBUILD (`./aur-packages upgrade` does).
- termux-language-server only runs on request (`./aur-packages check --manual`), as it has false positives: it only knows installed packages and paru's list of AUR packages (termux/termux-language-server#44), keeps the quotes of single-quoted names (termux/termux-language-server#43), takes names with an expansion like `"$pkgname-bin"` apart (termux/termux-language-server#45), and doesn't accept SPDX license expressions or `LicenseRef-` (termux/termux-language-server#24). Its warnings about x86_64 and vscode-powershell's split makedepends come from namcap, for the `case "$CARCH"` mappings and the editors its packages conflict over.
- Also lint with `namcap PKGBUILD` and `namcap` on the built package.
- Where an unquoted variable relies on word splitting, e.g. to add nothing when it's empty, use an array instead of disabling shellharden.
- PowerShell scripts (`.ps1`/`.psm1`) are PSScriptAnalyzer-clean with its default rules, information level included (`Invoke-ScriptAnalyzer -Path script.ps1`). Suppress a rule only where the code can't comply, with `[Diagnostics.CodeAnalysis.SuppressMessageAttribute('Rule', '', Justification = '…')]` saying why.
- Clean-chroot builds: `pkgctl build`, or `./aur-packages build` for a package with its dependencies from this repository. A local `makepkg -fCd` is fine for a quick check, but may lack makedepends.
- 32-bit packages (`lib32-*`) and packages that build 32-bit code depend on `lib32-*` packages of multilib, in their (make)depends; `./aur-packages build` builds those in a multilib chroot with `multilib-devel`, like `pkgctl build --repo multilib`.
