param([string]$SecretsFile = 'D:\LocalAI\signaldesk\delivery.env')
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $SecretsFile) {
    foreach ($line in Get-Content -LiteralPath $SecretsFile) {
        $value = $line.Trim()
        if ($value -eq '' -or $value.StartsWith('#')) { continue }
        $pair = $value -split '=', 2
        if ($pair.Count -ne 2 -or $pair[0] -notmatch '^[A-Z][A-Z0-9_]*$') { throw 'Invalid integration environment file.' }
        if ($pair[0] -notmatch '^SIGNALDESK_') { throw 'Only integration variables belong in this file.' }
        [Environment]::SetEnvironmentVariable($pair[0], $pair[1], 'Process')
    }
}
& "$PSScriptRoot\start.cmd"
