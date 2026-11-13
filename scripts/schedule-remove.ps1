<#
Remove every SignalDesk scheduled sweep created by schedule-install.ps1. Leaves your data untouched.

  powershell -ExecutionPolicy Bypass -File scripts\schedule-remove.ps1
#>
$ErrorActionPreference = 'Stop'
$tasks = Get-ScheduledTask -TaskPath '\SignalDesk\' -ErrorAction SilentlyContinue
if (-not $tasks) { Write-Output 'No SignalDesk scheduled tasks found.'; exit 0 }
foreach ($t in $tasks) {
    Unregister-ScheduledTask -TaskName $t.TaskName -TaskPath $t.TaskPath -Confirm:$false
    Write-Output "Removed '$($t.TaskName)'."
}
