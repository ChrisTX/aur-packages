# Completion of aur-packages and ./aur-packages for PowerShell. In $PROFILE:
# aur-packages completion pwsh | Out-String | Invoke-Expression
# The candidates come from the program itself (aur-packages __complete), so they always match the
# checkout's commands.

Register-ArgumentCompleter -Native -CommandName 'aur-packages', './aur-packages' -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    # The words up to the cursor, the one being typed last (empty after a space)
    $words = @($commandAst.CommandElements |
        Where-Object { $_.Extent.StartOffset -lt $cursorPosition } |
        ForEach-Object { $_.Extent.Text })
    if ($wordToComplete -eq '') {
        $words += ''
    }
    $program = $words[0]
    $arguments = @($words | Select-Object -Skip 1)
    $lines = @(& $program __complete @arguments 2>$null)
    if ($lines.Count -gt 0 -and $lines[0] -in ':files', ':dirs') {
        [System.Management.Automation.CompletionCompleters]::CompleteFilename($wordToComplete)
        return
    }
    foreach ($line in $lines) {
        $value, $description = $line -split "`t", 2
        if (-not $description) {
            $description = $value
        }
        [System.Management.Automation.CompletionResult]::new($value, $value, 'ParameterValue', $description)
    }
}
