# Contributing

Thanks for helping with these packages. Each top-level directory is one AUR package, added via `git subtree` and published with aurpublish: this repository is where the packages are developed, the AUR is where they're published. Pull requests here are welcome; the maintainer publishes merged changes to the AUR, each package's commits becoming its AUR history.

For problems with a package, open an issue here or comment on its AUR page. Problems of the software itself belong upstream, the `url` of the PKGBUILD.

## Getting started

The tools of the checks are all in the Arch Linux repositories, apart from PSScriptAnalyzer, which comes with `powershell-editor-services` (this repository, or the AUR), and Mago (`mago`, AUR):

```bash
sudo pacman -S --needed base-devel devtools pacman-contrib namcap nvchecker jq \
  prek shfmt shellcheck shellharden ruff biome tombi rumdl typos systemd-lsp \
  editorconfig-checker reuse
```

`./aur-packages build` also needs aurutils, and the aarch64 builds `qemu-user-static-binfmt`; publishing to the AUR (`./aur-packages pull` and `push`) needs aurpublish. Then install the git hooks, which run the checks on the staged files before each commit and check the commit message:

```bash
./aur-packages setup
```

`./aur-packages` manages all packages, or the packages given: `pull` and `push` (aurpublish, `push --exclude` to leave packages out), `adopt` (merges the AUR's history of a package that was on the AUR before, deleted or taken over, so it can be pushed), `updates` and `upgrade` (`pkgctl version check` and `upgrade` with each `.nvchecker.toml`), `check` (the hooks of `.pre-commit-config.yaml`), `build` (clean-chroot builds of packages and their dependencies from this repository, with aurutils), `sync` (copies `templates/package` into the packages), `setup` (installs the git hooks), `tray` (a daily update check with a tray icon, see [below](#update-check-in-the-tray)) and `list` (the packages). See `./aur-packages help`.

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

### Update check in the tray

`./aur-packages tray install` sets up a daily check of the packages of the checkout it's run from, and a tray icon that shows its result:

- The systemd user timer `aur-packages-updates.timer` runs `aur-packages updates --state --retry` once a day (and after a boot that missed it), through `aur-packages-updates.service`. The units are linked from `systemd/` of the checkout; a drop-in (`~/.config/systemd/user/aur-packages-updates.service.d/checkout.conf`) names the checkout.
- The result goes to `~/.local/state/aur-packages/updates.json`: the outdated packages with their current and new version, the packages whose check failed, and the time of the check. A package whose check failed (no network, say) keeps its entry of the previous check; if no package could be checked, the file says so and the service tries again later, less often the longer it fails. Packages that hit GitHub's rate limit aren't failures: they keep their entries too, and a transient timer (`aur-packages-updates-retry-*`) checks only them again a minute after the limit resets. `./aur-packages push` removes a pushed package from the outdated ones once the version it pushed is at least the new one, instead of leaving it there until the next check.
- The tray icon (`aur-packages-tray`, started on login by `~/.config/autostart/aur-packages-tray.desktop`) is hidden in the tray's overflow while everything is up to date, and shows up while packages are outdated. Its menu lists them, the time of the last check and failed checks, and has *Check now* and *Copy upgrade command* (`cd <checkout> && ./aur-packages upgrade <packages>`). A desktop notification announces each new upstream version once.

The tray icon speaks the tray protocol of Plasma (StatusNotifierItem with a dbusmenu menu) itself, with `python-gobject`; copying needs `wl-clipboard`. `./aur-packages tray remove` removes the units and the autostart entry again. Run `tray install` again after moving the checkout.

The check makes about 20 requests to the GitHub API, which allows 60 an hour without a token, shared with everything else on the same IP address: a few checks within an hour, e.g. with `./aur-packages updates`, exhaust it. A GitHub token without any scopes raises the limit to 5000 an hour; put it into `~/.config/nvchecker/keyfile.toml`, which `pkgctl version check` passes to nvchecker; only the `github` sources use it, not the `jq` ones that query api.github.com. The lookups of `./aur-packages commits` and `upgrade`, which move the pins (`_commit`) to a new version, use it as well, or without a keyfile the token `gh` is logged in with (`gh auth token`); `upgrade` fails when it can't move a pin, e.g. after the rate limit, as the package would build the old sources under the new version:

```toml
[keys]
github = "ghp_…"
```

## Language

Comments, documentation, package descriptions and commit messages are in British English: licence for the noun (license the verb), -ise and -isation (`optimise`, `customisation`), colour, behaviour, catalogue. Names and quotes keep their spelling: identifiers, paths and file names (`license=()`, `LICENSE`, `/usr/share/licenses`), the names of licences and products (the MIT License, Pluralize.NET), text taken from upstream, and the licence texts a package installs. typos checks the spelling, American spellings included, and the commit messages too; the names it leaves alone, and the terms of software it accepts as they are (artifact, analyzer), are in `.typos.toml` (change `templates/package`'s).

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
- Bump pkgrel when the built package changes (files, depends, licence, other metadata). Style-only or packaging-only changes don't get a bump.
- Go packages keep `GOPATH` inside `$srcdir`.
- PowerShell code goes into `.ps1`/`.psm1` files shipped as sources (annotated 0BSD in REUSE.toml), not inline `pwsh -Command '…'` blocks, so editors can support it. Pass values from the PKGBUILD as script parameters (`pwsh -NoProfile -NonInteractive -File "$srcdir/script.ps1" -Param "$value"`) instead of splicing shell variables into the code.

## Building from source

- Build dependencies from source wherever possible instead of using prebuilt binaries, especially PowerShell Gallery modules: build them from their upstream repositories (see powershell's `build-modules.ps1`/`powershell-modules.psm1`). For unmaintained or untagged modules, use the latest commit, as it may contain fixes that were never released.
- .NET packages build with the latest .NET SDK in the repositories (`dotnet-sdk`, versioned like `dotnet-sdk-10.0`), not the version upstream pins in `global.json`.
- Take .NET runtime packages from `dotnet-source-built-artifacts` instead of nuget.org where they're available, so they match the source-built .NET they run on (see powershell's `prepare()`: package source mapping in a generated `nuget.config`, `arch-x64` RID).
- Two selector packages decide where the build dependencies come from, and .NET packages makedepend on them rather than on what they choose:
  - `dotnet-build-deps-10.0` (one per .NET version, like the SDK the packages build with): .NET itself, the source-built one of Arch with its artifacts, the reference packages and IO.Ports' native package, pinned to the exact release of the SDK. `dotnet-build-deps-10.0-bin` picks Microsoft's `dotnet-sdk-bin` and nuget.org instead, pinned to its exact release the same way. Both are versioned like their SDK (`10.0.14.sdk114`: runtime, feature band and patch). They conflict with each other's packages, so two builds of .NET (different feature bands and versions) never mix. A .NET Arch Linux doesn't have yet only has the -bin selector, e.g. `dotnet-build-deps-11.0-bin` with Microsoft's prerelease (`dotnet-sdk-preview-bin`) for `powershell-preview`; `./aur-packages build` always uses it.
  - `powershell-build-deps` and `powershell-editor-services-build-deps`: our source-built libraries for powershell and PSES, separate packages so that building powershell alone doesn't build PSES's (makepkg installs the depends of all packages of a split PKGBUILD). `powershell-build-deps-bin` is split into a -bin package for each and ships nothing, so upstream's pins come from nuget.org.
  - NuGet packages are installed as local feeds: our libraries in `/usr/share/nuget/packages`, the packages built from the VMR's sources (the reference packages, IO.Ports' native package) in `/usr/share/nuget/dotnet-10.0/{reference-packages,packages}`, so a feed only holds packages of one build, like the source-built artifacts.
  - Consumers pick their feeds by what's installed (artifacts, our libraries in `/usr/share/nuget/packages`, the reference packages and IO.Ports' native package in `/usr/share/nuget/dotnet-10.0`), adding local feeds only when they exist (NuGet fails on missing ones). `_check_prebuilt` lets nuget.org binaries through only with the matching -bin selector installed (`pacman -T`).
- Publish .NET assemblies with ReadyToRun wherever possible (`-p:PublishReadyToRun=true`).
  - The SDK doesn't list `arch-x64` for crossgen2 packs, so ReadyToRun would use the `linux-x64` crossgen2 from nuget.org. Pass `-p:CustomAfterMicrosoftCommonTargets=$srcdir/crossgen2-pack.targets` (see powershell) to get the source-built one.
  - `PublishReadyToRun` only works for .NET (Core) projects. Assemblies targeting netstandard or .NET Framework, like most PowerShell modules, are compiled with crossgen2 directly against the runtime and `$PSHOME` (see powershell's `Invoke-ReadyToRunCompiler`). Skip copies of assemblies the runtime or `$PSHOME` already provide, as those aren't loaded.

## Per-package files

Besides `PKGBUILD` and `.SRCINFO`, every package has:

- `LICENSE` (0BSD, "Arch Linux Contributors") and `LICENSES/0BSD.txt` as a symlink to `../LICENSE`
- `REUSE.toml` annotating packaging files as 0BSD; patches derived from upstream are annotated with the upstream licence
- `.gitignore`: the toptal `archlinuxpackages` template, plus the checkout directory for git sources (e.g. `ergo/`) and downloaded sources the template doesn't cover (e.g. `*.nupkg`)
- An entry in README.md's package table, its description the package's pkgdesc: add it with a new package and keep it in sync when pkgdesc changes
- `.nvchecker.toml` for update checks (except VCS `-git` packages and sources without a usable upstream repo)
- `.editorconfig`, `.pre-commit-config.yaml` and `.typos.toml`, copies of `templates/package` (`./aur-packages sync`), so the package can be formatted and checked on its own. Change the template, not the copies; `./aur-packages sync` writes the top-level configuration from it as well.

## Packages outside the AUR

Two folders hold packages that are built and checked here, but never published to the AUR (`./aur-packages pull`, `push` and `adopt` refuse them):

- `local/<package>/`: packages of ours that aren't ours to publish, e.g. a rework of someone else's AUR package. They follow all the conventions of this file, like the packages at the top level; `git mv` moves one there or back.
- `overrides/<package>/`: Arch Linux's packages with changes of ours, e.g. fixes that aren't released yet. Each one is a subtree of Arch's packaging repository, with our changes as commits on top, and keeps Arch's style, so that Arch's updates merge cleanly and a fix can go back to Arch as it is:

  ```bash
  arch=https://gitlab.archlinux.org/archlinux/packaging/packages
  git subtree add -P overrides/ghidra "$arch/ghidra.git" main
  git subtree pull -P overrides/ghidra "$arch/ghidra.git" main
  ```

  Give the subtree's merge commit a summary like `overrides: add Arch Linux's ghidra packaging`, keeping the `git-subtree-*` lines of its message, which `git subtree` reads. An override's `pkgrel` stays below Arch's next release (`12.2-0.1` before Arch's `12.2-1`), so that pacman replaces it with Arch's package then; `./aur-packages overrides` compares them with Arch's repositories and says when one can go. Patches carry a comment with their upstream issue or pull request, like the backports in the other packages. Besides the patches, an override only adds a `.gitignore` for its downloads and their REUSE annotations. The style hooks leave overrides out; .SRCINFO, the checksums, REUSE and the downloads check still cover them. An override we keep for longer can get the files of `templates/package` and our conventions, and is then checked fully.

Commands take these packages by folder or by name (`./aur-packages build ghidra`), and `build` resolves dependencies on them, so a package builds against an override of its dependency. Their commits use the package name as the scope (`upgpkg: ghidra 12.2-0.1`, `ghidra-mcp: …`).

## Commits and aurpublish

- One commit per package.
- Message summary, the Arch convention rather than Conventional Commits (versions come from upstream, and each package's commits become its AUR history):
  - `upgpkg: <pkg> <ver>-<rel>` when pkgver/pkgrel changes, e.g. `upgpkg: powershell 7.6.9-22`.
  - Otherwise `<scope>: <summary>`, where the scope is the package directory, or the top-level file or directory for changes outside packages (e.g. `README.md:`, `aur-packages:`, `templates:`, `.github:`). The summary is lowercase and imperative (`add …`, `fix …`, `drop …`), without a trailing period.
- The prepare-commit-msg hook (`./aur-packages prepare-commit-msg`) fills in the summary of an empty message from the staged changes: the whole `upgpkg:` summary when they change a package's version (the staged .SRCINFO against HEAD's), else the scope, followed by the summary you write. Changes in several scopes get a comment saying so instead.
- The body lists the changes. The commit-msg hook (`./aur-packages commit-msg`) checks the summary: the scope has to exist, and the version in `upgpkg:` has to match the staged .SRCINFO. It checks the spelling of the message with typos as well.
- Regenerate .SRCINFO yourself (`makepkg --printsrcinfo > .SRCINFO`), the git hook only checks it. The hook (`./aur-packages setup`, prek or pre-commit) runs the checks below on the staged files and replaces aurpublish's hooks, so commit normally; don't bypass it.

## Building and checking

- Every disabled, skipped or removed test gets a comment saying why. If it's an upstream bug, link the upstream issue (open one if there is none yet). Disable as little as possible: a single test or context rather than a whole file.
- Everything passes `./aur-packages check`, which runs the hooks of `.pre-commit-config.yaml`: formatting (shfmt, ruff, Biome, tombi, rumdl, Mago, settings in `.editorconfig`), linting (shellcheck, shellharden, ruff, Biome, tombi, rumdl, systemd-lsp, PSScriptAnalyzer, Mago, editorconfig-checker), spelling (typos), `reuse lint`, the quoting of the metadata arrays, pinned commits that match a pkgver like git describe's (`2.2.r83.g4b8b3d3`, `./aur-packages pins`), up-to-date .SRCINFO files and checksums of the local sources, which a formatter may have changed (run `updpkgsums` then). Formatters fix files themselves; run the check again afterwards. After `updpkgsums`, which aligns the checksums its own way, run shfmt on the PKGBUILD (`./aur-packages upgrade` does).
- No editor modelines in any file (`# vim:set …`, `-*- mode -*-`): `.editorconfig` sets the indentation and the other settings for every editor.
- termux-language-server only runs on request (`./aur-packages check --manual`), as it has false positives: it only knows installed packages and paru's list of AUR packages (termux/termux-language-server#44), keeps the quotes of single-quoted names (termux/termux-language-server#43), takes names with an expansion like `"$pkgname-bin"` apart (termux/termux-language-server#45), and doesn't accept SPDX license expressions or `LicenseRef-` (termux/termux-language-server#24). Its warnings about x86_64 and vscode-powershell's split makedepends come from namcap, for the `case "$CARCH"` mappings and the editors its packages conflict over.
- Also lint with `namcap PKGBUILD` and `namcap` on the built package.
- Where an unquoted variable relies on word splitting, e.g. to add nothing when it's empty, use an array instead of disabling shellharden.
- PHP passes Mago's formatter, linter and analyser, warnings included. What a script only loads at runtime, like the classes of the software it's packaged with, is declared in a `*.stub.php` file next to it, which the package's `mago.toml` includes (see sourcebans-pp).
- PowerShell scripts (`.ps1`/`.psm1`) are PSScriptAnalyzer-clean with its default rules, information level included (`Invoke-ScriptAnalyzer -Path script.ps1`). Suppress a rule only where the code can't comply, with `[Diagnostics.CodeAnalysis.SuppressMessageAttribute('Rule', '', Justification = '…')]` saying why.
- Clean-chroot builds: `pkgctl build`, or `./aur-packages build` for a package with its dependencies from this repository. A local `makepkg -fCd` is fine for a quick check, but may lack makedepends.
- Sanitiser test builds: `./aur-packages build --sanitize=undefined` (or `address`, or `address,undefined`) builds packages and their dependencies with the sanitisers, by the flags of a makepkg.conf of its own, and keeps their repository; `check()` runs on them, and the reports go to the build's output. Never part of a PKGBUILD or a published package. Shared libraries take the sanitiser's runtime from the program that loads them, so a game server needs it in `LD_PRELOAD` (`/usr/lib/clang/<version>/lib/i386-pc-linux-gnu/libclang_rt.ubsan_standalone.so` for 32-bit servers).
- 32-bit packages (`lib32-*`) and packages that build 32-bit code depend on `lib32-*` packages of multilib, in their (make)depends; `./aur-packages build` builds those in a multilib chroot with `multilib-devel`, like `pkgctl build --repo multilib`.
