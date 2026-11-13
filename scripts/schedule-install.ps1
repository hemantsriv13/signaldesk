<#
Opt-in Windows schedule for SignalDesk sweeps. Creates one task per time, for the current user only,
running only while you are logged on. Nothing here needs administrator rights.

  powershell -ExecutionPolicy Bypass -File scripts\schedule-install.ps1                   # 08:00 and 20:00
  powershell -ExecutionPolicy Bypass -File scripts\schedule-install.ps1 -Times 07:30,19:30
  powershell -ExecutionPolicy Bypass -File scripts\schedule-install.ps1 -StartModel       # also start Colibri 4B first

Each task runs:  .venv\Scripts\python.exe -m signaldesk sweep --trigger schedule
If SignalDesk is open, the app does the sweep; otherwise the command sweeps and exits.
"Run as soon as possible after a missed start" is on, so a PC that was asleep at 08:00 runs once
when it wakes; Windows does not replay every missed time. Collection needs the PC to be on.
Remove with scripts\schedule-remove.ps1.
#>
param(
    [string[]]$Times = @('08:00', '20:00'),
    [switch]$StartModel
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw "Python environment not found at $python. Run scripts\setup.cmd first." }

$arguments = '-m signaldesk sweep --trigger schedule'
if ($StartModel) { $arguments += ' --start-model' }
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $repo

foreach ($t in $Times) {
    if ($t -notmatch '^\d{2}:\d{2}$') { throw "Use 24-hour times like 08:00 (got '$t')." }
    $name = "SignalDesk sweep $($t.Replace(':', ''))"
    $trigger = New-ScheduledTaskTrigger -Daily -At $t
    Register-ScheduledTask -TaskName $name -TaskPath '\SignalDesk\' -Action $action -Trigger $trigger -Settings $settings `
        -Principal $principal -Description 'SignalDesk sweep (opt-in). Remove with scripts\schedule-remove.ps1.' -Force | Out-Null
    Write-Output "Scheduled '$name' daily at $t (local time; set Windows to India Standard Time for IST)."
}
Write-Output "Done. Check them in Task Scheduler under \SignalDesk\, or run: Get-ScheduledTask -TaskPath '\SignalDesk\'"
