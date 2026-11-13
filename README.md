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
| `dotnet-build-deps` | the same, for the current .NET of Arch Linux (`dotnet-sdk`): stands in for `dotnet-build-deps-10.0` while that's the current version |
| `dotnet-build-deps-10.0-bin` | Microsoft's .NET 10 (`dotnet-sdk-10.0-bin`) and its packages from nuget.org, e.g. on Arch Linux ARM |
| `dotnet-build-deps-11.0-bin` (only choice) | Microsoft's .NET 11 (`dotnet-sdk-bin`) for `powershell-preview`, until Arch Linux has .NET 11 |
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
| [powershell-lts](https://aur.archlinux.org/packages/powershell-lts) | A cross-platform automation and configuration tool/framework (LTS release) | [![AUR version](https://img.shields.io/aur/version/powershell-lts?label=)](https://aur.archlinux.org/packages/powershell-lts) |
| [powershell-mmi](https://aur.archlinux.org/packages/powershell-mmi) | Microsoft.Management.Infrastructure (MMI) for PowerShell, built from its open source code | [![AUR version](https://img.shields.io/aur/version/powershell-mmi?label=)](https://aur.archlinux.org/packages/powershell-mmi) |
| [powershell-mmi-bin](https://aur.archlinux.org/packages/powershell-mmi-bin) | Microsoft.Management.Infrastructure (MMI) for PowerShell, Microsoft's build | [![AUR version](https://img.shields.io/aur/version/powershell-mmi-bin?label=)](https://aur.archlinux.org/packages/powershell-mmi-bin) |
| [powershell-pester-4](https://aur.archlinux.org/packages/powershell-pester-4) | Test and mock framework for PowerShell, Pester (version 4) | [![AUR version](https://img.shields.io/aur/version/powershell-pester-4?label=)](https://aur.archlinux.org/packages/powershell-pester-4) |
| [powershell-powershellget-v3](https://aur.archlinux.org/packages/powershell-powershellget-v3) | PowerShellGet v3, the compatibility module mapping PowerShellGet 2.x cmdlets onto PSResourceGet | [![AUR version](https://img.shields.io/aur/version/powershell-powershellget-v3?label=)](https://aur.archlinux.org/packages/powershell-powershellget-v3) |
| [powershell-preview](https://aur.archlinux.org/packages/powershell-preview) | A cross-platform automation and configuration tool/framework (preview release) | [![AUR version](https://img.shields.io/aur/version/powershell-preview?label=)](https://aur.archlinux.org/packages/powershell-preview) |
| [vscode-powershell](https://aur.archlinux.org/pkgbase/vscode-powershell) (`code-powershell`, `visual-studio-code-bin-powershell`, `vscodium-powershell`, `vscodium-bin-powershell`) | PowerShell extension for Visual Studio Code, using powershell-editor-services | [![AUR version](https://img.shields.io/aur/version/code-powershell?label=)](https://aur.archlinux.org/packages/code-powershell) |

### .NET

| Package | Description | AUR |
| --- | --- | --- |
| [dotnet-azure-core](https://aur.archlinux.org/packages/dotnet-azure-core) | Shared primitives, abstractions and helpers for .NET Azure SDK client libraries, Azure.Core (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-azure-core?label=)](https://aur.archlinux.org/packages/dotnet-azure-core) |
| [dotnet-azure-identity](https://aur.archlinux.org/packages/dotnet-azure-identity) | Microsoft Entra ID token authentication for the Azure SDK for .NET, Azure.Identity (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-azure-identity?label=)](https://aur.archlinux.org/packages/dotnet-azure-identity) |
| [dotnet-build-deps](https://aur.archlinux.org/packages/dotnet-build-deps) | Build dependencies of the .NET packages from the current source-built .NET of Arch Linux (meta package) | [![AUR version](https://img.shields.io/aur/version/dotnet-build-deps?label=)](https://aur.archlinux.org/packages/dotnet-build-deps) |
| [dotnet-build-deps-10.0](https://aur.archlinux.org/packages/dotnet-build-deps-10.0) | Build dependencies of the .NET packages from the source-built .NET 10.0 of Arch Linux (meta package) | [![AUR version](https://img.shields.io/aur/version/dotnet-build-deps-10.0?label=)](https://aur.archlinux.org/packages/dotnet-build-deps-10.0) |
| [dotnet-build-deps-10.0-bin](https://aur.archlinux.org/packages/dotnet-build-deps-10.0-bin) | Build dependencies of the .NET packages from Microsoft's build of .NET 10.0 and nuget.org (meta package) | [![AUR version](https://img.shields.io/aur/version/dotnet-build-deps-10.0-bin?label=)](https://aur.archlinux.org/packages/dotnet-build-deps-10.0-bin) |
| [dotnet-build-deps-11.0-bin](https://aur.archlinux.org/packages/dotnet-build-deps-11.0-bin) | Build dependencies of the .NET packages from Microsoft's build of .NET 11.0 and nuget.org (meta package) | [![AUR version](https://img.shields.io/aur/version/dotnet-build-deps-11.0-bin?label=)](https://aur.archlinux.org/packages/dotnet-build-deps-11.0-bin) |
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
| [dotnet-pluralize-net](https://aur.archlinux.org/packages/dotnet-pluralize-net) | Pluralise or singularise any English word, Pluralize.NET (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-pluralize-net?label=)](https://aur.archlinux.org/packages/dotnet-pluralize-net) |
| [dotnet-powershellstandard-library](https://aur.archlinux.org/packages/dotnet-powershellstandard-library) | Reference assembly for PowerShell modules that run on Windows PowerShell 5.1 and PowerShell 7 (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-powershellstandard-library?label=)](https://aur.archlinux.org/packages/dotnet-powershellstandard-library) |
| [dotnet-roslyn](https://aur.archlinux.org/packages/dotnet-roslyn) | The .NET Compiler Platform for C#, Microsoft.CodeAnalysis.Common and .CSharp (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-roslyn?label=)](https://aur.archlinux.org/packages/dotnet-roslyn) |
| [dotnet-source-build-reference-packages](https://aur.archlinux.org/packages/dotnet-source-build-reference-packages) | Reference, targeting and text-only NuGet packages of .NET's source build (SBRP), e.g. NETStandard.Library | [![AUR version](https://img.shields.io/aur/version/dotnet-source-build-reference-packages?label=)](https://aur.archlinux.org/packages/dotnet-source-build-reference-packages) |
| [dotnet-system-clientmodel](https://aur.archlinux.org/packages/dotnet-system-clientmodel) | Building blocks for .NET clients that call cloud services, System.ClientModel (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-clientmodel?label=)](https://aur.archlinux.org/packages/dotnet-system-clientmodel) |
| [dotnet-system-data-sqlclient](https://aur.archlinux.org/packages/dotnet-system-data-sqlclient) | The legacy SQL Server data provider for .NET, System.Data.SqlClient (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-data-sqlclient?label=)](https://aur.archlinux.org/packages/dotnet-system-data-sqlclient) |
| [dotnet-system-io-ports-native](https://aur.archlinux.org/packages/dotnet-system-io-ports-native) | Native library of System.IO.Ports for .NET on Linux, runtime.linux-*.runtime.native.System.IO.Ports (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-io-ports-native?label=)](https://aur.archlinux.org/packages/dotnet-system-io-ports-native) |
| [dotnet-system-reactive](https://aur.archlinux.org/packages/dotnet-system-reactive) | Reactive Extensions (Rx) for .NET, System.Reactive (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-system-reactive?label=)](https://aur.archlinux.org/packages/dotnet-system-reactive) |
| [dotnet-vs-threading](https://aur.archlinux.org/packages/dotnet-vs-threading) | Async synchronisation primitives, async collections, TPL and dataflow extensions, Microsoft.VisualStudio.Threading.Only (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-vs-threading?label=)](https://aur.archlinux.org/packages/dotnet-vs-threading) |
| [dotnet-vs-validation](https://aur.archlinux.org/packages/dotnet-vs-validation) | Common input validation and state verification utility methods, Microsoft.VisualStudio.Validation (NuGet package) | [![AUR version](https://img.shields.io/aur/version/dotnet-vs-validation?label=)](https://aur.archlinux.org/packages/dotnet-vs-validation) |
| [dotnet-wcf](https://aur.archlinux.org/packages/dotnet-wcf) | WCF client libraries for .NET, System.ServiceModel.* and System.Web.Services.Description (NuGet packages) | [![AUR version](https://img.shields.io/aur/version/dotnet-wcf?label=)](https://aur.archlinux.org/packages/dotnet-wcf) |

### SourceMod

Metamod:Source, SourceMod and their plugins and extensions for Source engine game servers, built from source against the system's libraries, with the Source SDKs and AMBuild they build with.

| Package | Description | AUR |
| --- | --- | --- |
| [ambuild](https://aur.archlinux.org/packages/ambuild) | AlliedModders' build system, used by SourceMod, SourcePawn and Metamod:Source | [![AUR version](https://img.shields.io/aur/version/ambuild?label=)](https://aur.archlinux.org/packages/ambuild) |
| [hl2sdk](https://aur.archlinux.org/packages/hl2sdk) | Source SDKs of the games Metamod:Source and SourceMod support, with their static libraries built from source (a build dependency) | [![AUR version](https://img.shields.io/aur/version/hl2sdk?label=)](https://aur.archlinux.org/packages/hl2sdk) |
| [lib32-jansson](https://aur.archlinux.org/packages/lib32-jansson) | C library for encoding, decoding and manipulating JSON data (32-bit) | [![AUR version](https://img.shields.io/aur/version/lib32-jansson?label=)](https://aur.archlinux.org/packages/lib32-jansson) |
| [lib32-libmaxminddb](https://aur.archlinux.org/packages/lib32-libmaxminddb) | MaxMindDB GeoIP2 database library (32-bit) | [![AUR version](https://img.shields.io/aur/version/lib32-libmaxminddb?label=)](https://aur.archlinux.org/packages/lib32-libmaxminddb) |
| [lib32-mariadb-connector-c](https://aur.archlinux.org/packages/lib32-mariadb-connector-c) | MariaDB Connector/C, the client library of MariaDB (32-bit) | [![AUR version](https://img.shields.io/aur/version/lib32-mariadb-connector-c?label=)](https://aur.archlinux.org/packages/lib32-mariadb-connector-c) |
| [lib32-postgresql-libs](https://aur.archlinux.org/packages/lib32-postgresql-libs) | PostgreSQL's client library, libpq, with its OAuth module (32-bit) | [![AUR version](https://img.shields.io/aur/version/lib32-postgresql-libs?label=)](https://aur.archlinux.org/packages/lib32-postgresql-libs) |
| [metamod-source](https://aur.archlinux.org/pkgbase/metamod-source) (`metamod-source`, `metamod-source-src`) | Metamod:Source, the plugin loader of SourceMod, for Source engine game servers, for the games of hl2sdk with Linux servers (the addons folder of a server) | [![AUR version](https://img.shields.io/aur/version/metamod-source?label=)](https://aur.archlinux.org/packages/metamod-source) |
| [metamod-source-dev](https://aur.archlinux.org/pkgbase/metamod-source-dev) (`metamod-source-dev`, `metamod-source-dev-src`) | Metamod:Source, a plugin loader for Source engine game servers (development builds) | [![AUR version](https://img.shields.io/aur/version/metamod-source-dev?label=)](https://aur.archlinux.org/packages/metamod-source-dev) |
| [sourcebans-pp](https://aur.archlinux.org/pkgbase/sourcebans-pp) (`sourcebans-pp`, `sourcemod-sourcebans-pp`) | SourceBans++, the admin, ban and communication management of SourceMod game servers | [![AUR version](https://img.shields.io/aur/version/sourcebans-pp?label=)](https://aur.archlinux.org/packages/sourcebans-pp) |
| [sourcemod](https://aur.archlinux.org/pkgbase/sourcemod) (`sourcemod`, `sourcemod-scripting`, `sourcemod-src`) | SourceMod, the scripting and administration platform for Source engine game servers | [![AUR version](https://img.shields.io/aur/version/sourcemod?label=)](https://aur.archlinux.org/packages/sourcemod) |
| [sourcemod-dev](https://aur.archlinux.org/pkgbase/sourcemod-dev) (`sourcemod-dev`, `sourcemod-dev-scripting`, `sourcemod-dev-src`) | SourceMod, the scripting and administration platform for Source engine game servers (development builds) | [![AUR version](https://img.shields.io/aur/version/sourcemod-dev?label=)](https://aur.archlinux.org/packages/sourcemod-dev) |
| [sourcemod-advertisements](https://aur.archlinux.org/packages/sourcemod-advertisements) | Advertisements, a SourceMod plugin displaying messages on game servers (in the addons folder of sourcemod) | [![AUR version](https://img.shields.io/aur/version/sourcemod-advertisements?label=)](https://aur.archlinux.org/packages/sourcemod-advertisements) |
| [sourcemod-multicolors](https://aur.archlinux.org/packages/sourcemod-multicolors) | Multi-Colors, SourceMod include files for coloured chat messages in any game (Colors and More Colors) | [![AUR version](https://img.shields.io/aur/version/sourcemod-multicolors?label=)](https://aur.archlinux.org/packages/sourcemod-multicolors) |
| [sourcemod-smjansson](https://aur.archlinux.org/packages/sourcemod-smjansson) | SMJansson, a JSON extension of SourceMod (in the addons folder of sourcemod) | [![AUR version](https://img.shields.io/aur/version/sourcemod-smjansson?label=)](https://aur.archlinux.org/packages/sourcemod-smjansson) |
| [sourcemod-sourcebans-pp-discord-forward](https://aur.archlinux.org/packages/sourcemod-sourcebans-pp-discord-forward) | SourceBans++ Discord Forward, a SourceMod plugin forwarding bans, comms blocks and reports to Discord webhooks | [![AUR version](https://img.shields.io/aur/version/sourcemod-sourcebans-pp-discord-forward?label=)](https://aur.archlinux.org/packages/sourcemod-sourcebans-pp-discord-forward) |
| [sourcemod-steamworks](https://aur.archlinux.org/packages/sourcemod-steamworks) | SteamWorks, a SourceMod extension exposing Steamworks functions (in the addons folder of sourcemod) | [![AUR version](https://img.shields.io/aur/version/sourcemod-steamworks?label=)](https://aur.archlinux.org/packages/sourcemod-steamworks) |

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

### Not on the AUR

Packages built here for our own use, with `./aur-packages build`, and never published to the AUR.

`local/` has packages of ours that aren't (or aren't yet) ours to publish:

| Package | Description | Why |
| --- | --- | --- |
| [ghidra-mcp](local/ghidra-mcp) | MCP server for Ghidra: a Ghidra extension with an HTTP API for reverse engineering, and the MCP bridge to it | A rework of the [AUR package](https://aur.archlinux.org/packages/ghidra-mcp), whose maintainer it's [offered to](https://aur.archlinux.org/packages/ghidra-mcp#comment-1090246) |
| [pmd](local/pmd) | Extensible cross-language static code analyser | An update of the [AUR package](https://aur.archlinux.org/packages/pmd) (7.12.0, out of date since March 2026), built from source, for the linting of Java code |

`overrides/` has Arch Linux's packages with changes of ours, as subtrees of Arch's packaging in Arch's style, versioned below Arch's next release (e.g. `12.2-0.1`), which replaces them. `./aur-packages overrides` says when Arch has caught up and one can go:

| Package | Changes | Until |
| --- | --- | --- |
| [ghidra](overrides/ghidra) | 12.2, and fixes of the no-return analysis that truncates functions in 32-bit GCC binaries | [ghidra#9770](https://github.com/NationalSecurityAgency/ghidra/pull/9770) and [ghidra#10173](https://github.com/NationalSecurityAgency/ghidra/issues/10173) are released, and Arch Linux has 12.2 |

## Repository layout

- `<package>/`: one AUR package each, added with `git subtree` and published with [aurpublish](https://github.com/eli-schwartz/aurpublish). Each one has its own `.editorconfig` and `.pre-commit-config.yaml` (copies of `templates/package`), so its AUR repository can be formatted and checked on its own.
- `local/<package>/` and `overrides/<package>/`: packages built here but never published to the AUR, see [above](#not-on-the-aur). The overrides keep Arch Linux's style, and only the checks that aren't about style run on them.
- `aur-packages`: manages the packages: pulling and pushing them, update checks and upgrades with each `.nvchecker.toml`, the checks and clean-chroot builds of packages with their dependencies from this repository (`./aur-packages build powershell-full`, also cross-built or under QEMU for `aarch64`). It can go on PATH, with completions for bash, zsh, fish and PowerShell (see [CONTRIBUTING.md](CONTRIBUTING.md#aur-packages-in-your-shell)). See `./aur-packages help`.
- `completions/`: the shell completions of `aur-packages`.
- `aur-packages-tray` and `systemd/`: the tray icon and the user units of the daily update check (`./aur-packages tray install`, see [CONTRIBUTING.md](CONTRIBUTING.md#update-check-in-the-tray)).
- `templates/`: the files shared by all packages.
- `LICENSES/` and `REUSE.toml`: the licences, in the [REUSE](https://reuse.software/) format.

## Contributing

Issues and pull requests are welcome, as are comments on the AUR pages. See [CONTRIBUTING.md](CONTRIBUTING.md) for the setup and the conventions of the packages, and [SECURITY.md](SECURITY.md) for reporting security issues.

## Licence

The packaging files (PKGBUILDs, scripts, configuration) are licensed under the [0BSD](LICENSE) licence, like the packaging of Arch Linux. Patches derived from upstream code keep the upstream licence, as their package's `REUSE.toml` says. The packaged software itself is licensed by its authors, as each PKGBUILD's `license` says.
