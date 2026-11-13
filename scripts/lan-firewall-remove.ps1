<#
Remove the firewall rule created by lan-firewall.ps1. Run in an elevated PowerShell.
  powershell -ExecutionPolicy Bypass -File scripts\lan-firewall-remove.ps1
#>
$rules = Get-NetFirewallRule -Group 'SignalDesk' -ErrorAction SilentlyContinue
if (-not $rules) { Write-Output 'No SignalDesk firewall rules found.'; exit 0 }
$rules | ForEach-Object { Write-Output "Removing '$($_.DisplayName)'" }
Remove-NetFirewallRule -Group 'SignalDesk'
