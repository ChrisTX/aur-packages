# AUR packages

[![Checks](https://github.com/ChrisTX/aur-packages/actions/workflows/check.yml/badge.svg)](https://github.com/ChrisTX/aur-packages/actions/workflows/check.yml)

The PKGBUILDs of the [Arch User Repository](https://aur.archlinux.org/) packages maintained by [ChrisTX](https://aur.archlinux.org/account/ChrisTX). They're developed in this repository, one top-level directory per package, and published to the AUR, which is where you install them from.

## PowerShell from source

The largest part of this repository builds PowerShell and its ecosystem entirely from source, on the source-built .NET of Arch Linux:

- `powershell` builds PowerShell and the modules it ships (PSReadLine, PSResourceGet, ThreadJob, …) from their upstream repositories, instead of taking them from the PowerShell Gallery.
- Its .NET dependencies are packages of their own, NuGet packages built from source (`dotnet-*`), installed as a local feed in `/usr/share/nuget/packages`.
- Assemblies are compiled ahead of time with ReadyToRun, and the packages build for `x86_64` and `aarch64`.
- The editor services, the VS Code extension, DSC v3, MMI and Pester 4 are built from source as well.

Building all of that takes a while. Selector packages let you pick prebuilt parts instead, without changing the PKGBUILDs:

| Install first | to build with |
| --- | --- |
| `dotnet-build-deps-10.0` (default) | the source-built .NET of Arch Linux and its artifacts |
| `dotnet-build-deps-10.0-bin` | Microsoft's .NET (`dotnet-sdk-bin`) and its packages from nuget.org, e.g. on Arch Linux ARM |
| `powershell-build-deps` (default) | the libraries of this repository, built from source |
| `powershell-build-deps-bin` | the libraries from nuget.org |

## Installing

With an AUR helper, e.g. `paru -S powershell`, or by hand:

```bash
git clone https://aur.archlinux.org/powershell.git
cd powershell
makepkg -si
```

## Packages

### PowerShell

| Package | Description | AUR |
| --- | --- | --- |
| [powershell](https://aur.archlinux.org/packages/powershell) | A cross-platform automation and configuration tool/framework | [![AUR version](https://img.shields.io/aur/version/powershell?label=)](https://aur.archlinux.org/packages/powershell) |
| [powershell-build-deps](https://aur.archlinux.org/packages/powershell-build-deps) | Libraries PowerShell builds against, built from source (meta package) | [![AUR version](https://img.shields.io/aur/version/powershell-build-deps?label=)](https://aur.archlinux.org/packages/powershell-build-deps) |
| [powershell-build-deps-bin](https://aur.archlinux.org/pkgbase/powershell-build-deps-bin) (`powershell-build-deps-bin`, `powershell-editor-services-build-deps-bin`) | Lets PowerShell build against the libraries from nuget.org instead of building them from source (meta package) | [![AUR version](https://img.shields.io/aur/version/powershell-build-deps-bin?label=)](https://aur.archlinux.org/packages/powershell-build-deps-bin) |
| [powershell-dsc](https://aur.archlinux.org/packages/powershell-dsc) | Microsoft Desired State Configuration v3 platform | [![AUR version](https://img.shields.io/aur/version/powershell-dsc?label=)](https://aur.archlinux.org/packages/powershell-dsc) |
| [powershell-editor-services](https://aur.archlinux.org/packages/powershell-editor-services) | A common platform for PowerShell development support in any editor or application | [![AUR version](https://img.shields.io/aur/version/powershell-editor-services?label=)](https://aur.archlinux.org/packages/powershell-editor-services) |
| [powershell-editor-services-build-deps](https://aur.archlinux.org/packages/powershell-editor-services-build-deps) | Libraries the PowerShell editor services build against, built from source (meta package) | [![AUR version](https://img.shields.io/aur/version/powershell-editor-services-build-deps?label=)](https://aur.archlinux.org/packages/powershell-editor-services-build-deps) |
| [powershell-mmi](https://aur.archlinux.org/packages/powershell-mmi) | Microsoft.Management.Infrastructure (MMI) for PowerShell, built from its open source code | [![AUR version](https://img.shields.io/aur/version/powershell-mmi?label=)](https://aur.archlinux.org/packages/powershell-mmi) |
| [powershell-mmi-bin](https://aur.archlinux.org/packages/powershell-mmi-bin) | Microsoft.Management.Infrastructure (MMI) for PowerShell, Microsoft's build | [![AUR version](https://img.shields.io/aur/version/powershell-mmi-bin?label=)](https://aur.archlinux.org/packages/powershell-mmi-bin) |
| [powershell-pester-4](https://aur.archlinux.org/packages/powershell-pester-4) | Test and mock framework for PowerShell, Pester (version 4) | [![AUR version](https://img.shields.io/aur/version/powershell-pester-4?label=)](https://aur.archlinux.org/packages/powershell-pester-4) |
| [powershell-powershellget-v3](https://aur.archlinux.org/packages/powershell-powershellget-v3) | PowerShellGet v3, the compatibility module mapping PowerShellGet 2.x cmdlets onto PSResourceGet | [![AUR version](https://img.shields.io/aur/version/powershell-powershellget-v3?label=)](https://aur.archlinux.org/packages/powershell-powershellget-v3) |
| [vscode-powershell](https://aur.archlinux.org/pkgbase/vscode-powershell) (`code-powershell`, `visual-studio-code-bin-powershell`, `vscodium-powershell`, `vscodium-bin-powershell`) | PowerShell extension for Visual Studio Code, using powershell-editor-services | [![AUR version](https://img.shields.io/aur/version/code-powershell?label=)](https://aur.archlinux.org/packages/code-powershell) |

### .NET

| Package | Description | AUR |
| --- | --- | --- |
| [dotnet-azure-core](https://aur.archlinux.org/packages/dotnet-azure-core) | Shared primitives, abstractions and helpers for .NET Azure SDK client libraries, Azure.Core (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-azure-core?label=)](https://aur.archlinux.org/packages/dotnet-azure-core) |
| [dotnet-azure-identity](https://aur.archlinux.org/packages/dotnet-azure-identity) | Microsoft Entra ID token authentication for the Azure SDK for .NET, Azure.Identity (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-azure-identity?label=)](https://aur.archlinux.org/packages/dotnet-azure-identity) |
| [dotnet-build-deps-10.0](https://aur.archlinux.org/packages/dotnet-build-deps-10.0) | Build dependencies of the .NET packages from the source-built .NET 10.0 of Arch Linux (meta package) | [![AUR version](https://img.shields.io/aur/version/dotnet-build-deps-10.0?label=)](https://aur.archlinux.org/packages/dotnet-build-deps-10.0) |
| [dotnet-build-deps-10.0-bin](https://aur.archlinux.org/packages/dotnet-build-deps-10.0-bin) | Build dependencies of the .NET packages from Microsoft's build of .NET 10.0 and nuget.org (meta package) | [![AUR version](https://img.shields.io/aur/version/dotnet-build-deps-10.0-bin?label=)](https://aur.archlinux.org/packages/dotnet-build-deps-10.0-bin) |
| [dotnet-gherkin-5](https://aur.archlinux.org/packages/dotnet-gherkin-5) | Parser for the Gherkin language of Cucumber, Gherkin (NuGet package, version 5) | [![AUR version](https://img.shields.io/aur/version/dotnet-gherkin-5?label=)](https://aur.archlinux.org/packages/dotnet-gherkin-5) |
| [dotnet-humanizer-core-2](https://aur.archlinux.org/packages/dotnet-humanizer-core-2) | Turns strings, type names, enum fields and dates into a human friendly format, 2.x (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-humanizer-core-2?label=)](https://aur.archlinux.org/packages/dotnet-humanizer-core-2) |
| [dotnet-json-more-net-2](https://aur.archlinux.org/packages/dotnet-json-more-net-2) | Extended functionality for System.Text.Json, 2.x (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-json-more-net-2?label=)](https://aur.archlinux.org/packages/dotnet-json-more-net-2) |
| [dotnet-jsonpointer-net-5](https://aur.archlinux.org/packages/dotnet-jsonpointer-net-5) | JSON Pointer built on System.Text.Json, 5.x (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-jsonpointer-net-5?label=)](https://aur.archlinux.org/packages/dotnet-jsonpointer-net-5) |
| [dotnet-jsonschema-net-7](https://aur.archlinux.org/packages/dotnet-jsonschema-net-7) | JSON Schema built on System.Text.Json, 7.x (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-jsonschema-net-7?label=)](https://aur.archlinux.org/packages/dotnet-jsonschema-net-7) |
| [dotnet-markdig](https://aur.archlinux.org/packages/dotnet-markdig) | Fast, powerful, CommonMark compliant, extensible Markdown processor for .NET (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-markdig?label=)](https://aur.archlinux.org/packages/dotnet-markdig) |
| [dotnet-mediatr-12](https://aur.archlinux.org/packages/dotnet-mediatr-12) | Simple mediator implementation in .NET, MediatR 12 and MediatR.Contracts (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-mediatr-12?label=)](https://aur.archlinux.org/packages/dotnet-mediatr-12) |
| [dotnet-microsoft-identity-client](https://aur.archlinux.org/packages/dotnet-microsoft-identity-client) | Microsoft Authentication Library for .NET (MSAL.NET), Microsoft.Identity.Client and its extensions (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-microsoft-identity-client?label=)](https://aur.archlinux.org/packages/dotnet-microsoft-identity-client) |
| [dotnet-nerdbank-streams](https://aur.archlinux.org/packages/dotnet-nerdbank-streams) | Streams for full duplex in-proc communication, wrap a WebSocket, split a stream into multiple channels, Nerdbank.Streams (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-nerdbank-streams?label=)](https://aur.archlinux.org/packages/dotnet-nerdbank-streams) |
| [dotnet-newtonsoft-json](https://aur.archlinux.org/packages/dotnet-newtonsoft-json) | Popular high-performance JSON framework for .NET (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-newtonsoft-json?label=)](https://aur.archlinux.org/packages/dotnet-newtonsoft-json) |
| [dotnet-omnisharp-extensions](https://aur.archlinux.org/packages/dotnet-omnisharp-extensions) | Language Server Protocol and Debug Adapter Protocol for .NET, OmniSharp.Extensions.* (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-omnisharp-extensions?label=)](https://aur.archlinux.org/packages/dotnet-omnisharp-extensions) |
| [dotnet-pluralize-net](https://aur.archlinux.org/packages/dotnet-pluralize-net) | Pluralize or singularize any English word, Pluralize.NET (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-pluralize-net?label=)](https://aur.archlinux.org/packages/dotnet-pluralize-net) |
| [dotnet-powershellstandard-library](https://aur.archlinux.org/packages/dotnet-powershellstandard-library) | Reference assembly for PowerShell modules that run on Windows PowerShell 5.1 and PowerShell 7 (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-powershellstandard-library?label=)](https://aur.archlinux.org/packages/dotnet-powershellstandard-library) |
| [dotnet-roslyn](https://aur.archlinux.org/packages/dotnet-roslyn) | The .NET Compiler Platform for C#, Microsoft.CodeAnalysis.Common and .CSharp (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-roslyn?label=)](https://aur.archlinux.org/packages/dotnet-roslyn) |
| [dotnet-source-build-reference-packages](https://aur.archlinux.org/packages/dotnet-source-build-reference-packages) | Reference, targeting and text-only NuGet packages of .NET's source build (SBRP), e.g. NETStandard.Library | [![AUR version](https://img.shields.io/aur/version/dotnet-source-build-reference-packages?label=)](https://aur.archlinux.org/packages/dotnet-source-build-reference-packages) |
| [dotnet-system-clientmodel](https://aur.archlinux.org/packages/dotnet-system-clientmodel) | Building blocks for .NET clients that call cloud services, System.ClientModel (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-clientmodel?label=)](https://aur.archlinux.org/packages/dotnet-system-clientmodel) |
| [dotnet-system-data-sqlclient](https://aur.archlinux.org/packages/dotnet-system-data-sqlclient) | The legacy SQL Server data provider for .NET, System.Data.SqlClient (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-data-sqlclient?label=)](https://aur.archlinux.org/packages/dotnet-system-data-sqlclient) |
| [dotnet-system-io-ports-native](https://aur.archlinux.org/packages/dotnet-system-io-ports-native) | Native library of System.IO.Ports for .NET on Linux, runtime.linux-*.runtime.native.System.IO.Ports (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-io-ports-native?label=)](https://aur.archlinux.org/packages/dotnet-system-io-ports-native) |
| [dotnet-system-reactive](https://aur.archlinux.org/packages/dotnet-system-reactive) | Reactive Extensions (Rx) for .NET, System.Reactive (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-reactive?label=)](https://aur.archlinux.org/packages/dotnet-system-reactive) |
| [dotnet-vs-threading](https://aur.archlinux.org/packages/dotnet-vs-threading) | Async synchronization primitives, async collections, TPL and dataflow extensions, Microsoft.VisualStudio.Threading.Only (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-vs-threading?label=)](https://aur.archlinux.org/packages/dotnet-vs-threading) |
| [dotnet-vs-validation](https://aur.archlinux.org/packages/dotnet-vs-validation) | Common input validation and state verification utility methods, Microsoft.VisualStudio.Validation (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-vs-validation?label=)](https://aur.archlinux.org/packages/dotnet-vs-validation) |
| [dotnet-wcf](https://aur.archlinux.org/packages/dotnet-wcf) | WCF client libraries for .NET, System.ServiceModel.* and System.Web.Services.Description (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-wcf?label=)](https://aur.archlinux.org/packages/dotnet-wcf) |

### Other

| Package | Description | AUR |
| --- | --- | --- |
| [cockpit-session-recording](https://aur.archlinux.org/packages/cockpit-session-recording) | Cockpit UI for session recording | [![AUR version](https://img.shields.io/aur/version/cockpit-session-recording?label=)](https://aur.archlinux.org/packages/cockpit-session-recording) |
| [crossplane-gixy](https://aur.archlinux.org/packages/crossplane-gixy) | Reliable and fast NGINX configuration file parser | [![AUR version](https://img.shields.io/aur/version/crossplane-gixy?label=)](https://aur.archlinux.org/packages/crossplane-gixy) |
| [crowdsec-nginx-bouncer](https://aur.archlinux.org/packages/crowdsec-nginx-bouncer) | CrowdSec bouncer for Nginx | [![AUR version](https://img.shields.io/aur/version/crowdsec-nginx-bouncer?label=)](https://aur.archlinux.org/packages/crowdsec-nginx-bouncer) |
| [cryptpad](https://aur.archlinux.org/packages/cryptpad) | Realtime collaborative visual editor with zero knowledge server | [![AUR version](https://img.shields.io/aur/version/cryptpad?label=)](https://aur.archlinux.org/packages/cryptpad) |
| [cryptpad-sso](https://aur.archlinux.org/packages/cryptpad-sso) | SSO plugin for Cryptpad | [![AUR version](https://img.shields.io/aur/version/cryptpad-sso?label=)](https://aur.archlinux.org/packages/cryptpad-sso) |
| [download-with-kget-native-git](https://aur.archlinux.org/packages/download-with-kget-native-git) | KGet extension native handler | [![AUR version](https://img.shields.io/aur/version/download-with-kget-native-git?label=)](https://aur.archlinux.org/packages/download-with-kget-native-git) |
| [ergochat](https://aur.archlinux.org/packages/ergochat) | Modern IRC server written in Go | [![AUR version](https://img.shields.io/aur/version/ergochat?label=)](https://aur.archlinux.org/packages/ergochat) |
| [ergochat-dnsbl](https://aur.archlinux.org/packages/ergochat-dnsbl) | DNSBL plugin for the IRC server Ergo | [![AUR version](https://img.shields.io/aur/version/ergochat-dnsbl?label=)](https://aur.archlinux.org/packages/ergochat-dnsbl) |
| [ergochat-ldap](https://aur.archlinux.org/packages/ergochat-ldap) | LDAP plugin for the IRC server Ergo | [![AUR version](https://img.shields.io/aur/version/ergochat-ldap?label=)](https://aur.archlinux.org/packages/ergochat-ldap) |
| [flarectl](https://aur.archlinux.org/packages/flarectl) | CLI application for interacting with a Cloudflare account | [![AUR version](https://img.shields.io/aur/version/flarectl?label=)](https://aur.archlinux.org/packages/flarectl) |
| [flarectl-bin](https://aur.archlinux.org/packages/flarectl-bin) | CLI application for interacting with a Cloudflare account | [![AUR version](https://img.shields.io/aur/version/flarectl-bin?label=)](https://aur.archlinux.org/packages/flarectl-bin) |
| [fortitude](https://aur.archlinux.org/packages/fortitude) | Fortran linter, inspired by (and built upon) Ruff | [![AUR version](https://img.shields.io/aur/version/fortitude?label=)](https://aur.archlinux.org/packages/fortitude) |
| [gotlsaflare](https://aur.archlinux.org/packages/gotlsaflare) | Update TLSA DANE records on Cloudflare from X509 certificate | [![AUR version](https://img.shields.io/aur/version/gotlsaflare?label=)](https://aur.archlinux.org/packages/gotlsaflare) |
| [ircdog](https://aur.archlinux.org/packages/ircdog) | Tool for sending and receiving raw IRC protocol lines | [![AUR version](https://img.shields.io/aur/version/ircdog?label=)](https://aur.archlinux.org/packages/ircdog) |
| [ltex-ls-plus](https://aur.archlinux.org/packages/ltex-ls-plus) | Language server for LanguageTool with support for LaTeX, Markdown, and others | [![AUR version](https://img.shields.io/aur/version/ltex-ls-plus?label=)](https://aur.archlinux.org/packages/ltex-ls-plus) |
| [modsecurity-crs](https://aur.archlinux.org/packages/modsecurity-crs) | OWASP ModSecurity Core Rule Set | [![AUR version](https://img.shields.io/aur/version/modsecurity-crs?label=)](https://aur.archlinux.org/packages/modsecurity-crs) |
| [mogui](https://aur.archlinux.org/packages/mogui) | Graphical user interface for Environment Modules | [![AUR version](https://img.shields.io/aur/version/mogui?label=)](https://aur.archlinux.org/packages/mogui) |
| [nginx-language-server](https://aur.archlinux.org/packages/nginx-language-server) | Language Server for nginx.conf | [![AUR version](https://img.shields.io/aur/version/nginx-language-server?label=)](https://aur.archlinux.org/packages/nginx-language-server) |
| [python-a2s](https://aur.archlinux.org/packages/python-a2s) | Python package for querying Source and GoldSource servers | [![AUR version](https://img.shields.io/aur/version/python-a2s?label=)](https://aur.archlinux.org/packages/python-a2s) |
| [tcos-pkcs11](https://aur.archlinux.org/packages/tcos-pkcs11) | PKCS#11 driver for TeleSec TCOS smartcards | [![AUR version](https://img.shields.io/aur/version/tcos-pkcs11?label=)](https://aur.archlinux.org/packages/tcos-pkcs11) |
| [tlog](https://aur.archlinux.org/packages/tlog) | Terminal I/O logger | [![AUR version](https://img.shields.io/aur/version/tlog?label=)](https://aur.archlinux.org/packages/tlog) |

## Repository layout

- `<package>/`: one AUR package each, added with `git subtree` and published with [aurpublish](https://github.com/eli-schwartz/aurpublish). Each one has its own `.editorconfig` and `.pre-commit-config.yaml` (copies of `templates/package`), so its AUR repository can be formatted and checked on its own.
- `aur-packages`: manages the packages: pulling and pushing them, update checks and upgrades with each `.nvchecker.toml`, the checks and clean-chroot builds of packages with their dependencies from this repository (`./aur-packages build powershell-full`, also cross-built or under QEMU for `aarch64`). It can go on PATH, with completions for bash, zsh, fish and PowerShell (see [CONTRIBUTING.md](CONTRIBUTING.md#aur-packages-in-your-shell)). See `./aur-packages help`.
- `completions/`: the shell completions of `aur-packages`.
- `templates/`: the files shared by all packages.
- `LICENSES/` and `REUSE.toml`: the licenses, in the [REUSE](https://reuse.software/) format.

## Contributing

Issues and pull requests are welcome, as are comments on the AUR pages. See [CONTRIBUTING.md](CONTRIBUTING.md) for the setup and the conventions of the packages, and [SECURITY.md](SECURITY.md) for reporting security issues.

## License

The packaging files (PKGBUILDs, scripts, configuration) are licensed under the [0BSD](LICENSE) license, like the packaging of Arch Linux. Patches derived from upstream code keep the upstream license, as their package's `REUSE.toml` says. The packaged software itself is licensed by its authors, as each PKGBUILD's `license` says.
