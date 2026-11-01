# Completion of aur-packages and ./aur for PowerShell, not for aur, which is aurutils'. In $PROFILE:
# aur-packages completion pwsh | Out-String | Invoke-Expression

Register-ArgumentCompleter -Native -CommandName 'aur-packages', './aur' -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    $commands = [ordered]@{
        'pull'       = 'Pull the packages from the AUR'
        'push'       = 'Check, then push the packages to the AUR'
        'updates'    = 'Show which packages have a newer upstream version'
        'upgrade'    = 'Upgrade the packages to their latest upstream version'
        'check'      = 'Run the checks of .pre-commit-config.yaml'
        'commits'    = 'Show the upstream commits of the pinned _commit values'
        'build'      = 'Build packages or a template with their dependencies'
        'sync'       = 'Copy templates/package into the packages'
        'setup'      = 'Install the git hooks'
        'commit-msg' = 'Check a commit message'
        'list'       = 'List the packages or the build templates'
        'completion' = 'Print the completion script of a shell'
        'help'       = 'Show the help'
    }
    $options = @{
        'push'    = @('--nocheck')
        'check'   = @('--manual')
        'commits' = @('--update')
        'sync'    = @('--check')
        'list'    = @('--templates')
        'build'   = @('--chroot', '--local', '--install', '--dry-run', '-n', '--keep', '--dotnet-bin', '--libs-bin',
            '--target', '--repo')
    }
    $withPackages = @('pull', 'push', 'updates', 'upgrade', 'check', 'commits', 'build', 'sync')

    # The packages (or with --templates the build templates) of the checkout the command works on, from
    # the command itself
    $program = $commandAst.CommandElements[0].Extent.Text
    function Get-AurPackageName {
        param([switch] $Template)
        $arguments = @('list') + @(if ($Template) { '--templates' })
        & $program @arguments 2>$null
    }

    function ConvertTo-CompletionResult {
        param([string] $Text, [string] $ToolTip = $Text, [string] $Type = 'ParameterValue')
        [System.Management.Automation.CompletionResult]::new($Text, $Text, $Type, $ToolTip)
    }

    # The files or folders starting with the word being completed, with its folder in front
    function Get-PathResult {
        param([switch] $Directory)
        $folder = if ($wordToComplete -match '^(.*/)') { $Matches[1] } else { '' }
        Get-ChildItem -Path "$wordToComplete*" -Directory:$Directory -ErrorAction Ignore | ForEach-Object {
            ConvertTo-CompletionResult -Text "$folder$($_.Name)" -Type $(if ($_.PSIsContainer) { 'ProviderContainer' } else { 'ProviderItem' })
        }
    }

    # The words before the one being completed, after the program's name
    $words = @($commandAst.CommandElements | Select-Object -Skip 1 |
            Where-Object { $_.Extent.EndOffset -lt $cursorPosition } | ForEach-Object { $_.Extent.Text })
    $command = $words | Where-Object { $_ -notlike '-*' } | Select-Object -First 1
    $previous = if ($words.Count) { $words[-1] } else { '' }
    $afterCommand = $words.Count - [array]::IndexOf($words, $command) - 1

    $candidates = if (-not $command) {
        $commands.GetEnumerator() | Where-Object Key -Like "$wordToComplete*" | ForEach-Object {
            ConvertTo-CompletionResult -Text $_.Key -ToolTip $_.Value
        }
    } elseif ($command -eq 'build' -and $previous -eq '--target') {
        'aarch64', 'aarch64-native' | ForEach-Object { ConvertTo-CompletionResult -Text $_ }
    } elseif ($command -eq 'build' -and $previous -eq '--repo') {
        Get-PathResult -Directory
    } elseif ($command -eq 'commit-msg') {
        if ($afterCommand -eq 0) {
            Get-PathResult
        }
    } elseif ($command -eq 'completion') {
        if ($afterCommand -eq 0) {
            'bash', 'zsh', 'fish', 'pwsh' | ForEach-Object { ConvertTo-CompletionResult -Text $_ }
        }
    } elseif ($wordToComplete -like '-*') {
        $options[$command] | ForEach-Object { ConvertTo-CompletionResult -Text $_ -Type 'ParameterName' }
    } elseif ($command -in $withPackages) {
        Get-AurPackageName | ForEach-Object { ConvertTo-CompletionResult -Text $_ }
        if ($command -eq 'build') {
            Get-AurPackageName -Template | ForEach-Object { ConvertTo-CompletionResult -Text $_ -ToolTip "$_ (build template)" }
        }
    }
    $candidates | Where-Object CompletionText -Like "$wordToComplete*"
}
