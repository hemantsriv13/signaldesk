<#
Opt-in: allow ONLY your listed devices on your private Wi-Fi to reach SignalDesk's HTTPS port.
Run in an elevated PowerShell (Run as administrator). Remove with scripts\lan-firewall-remove.ps1.

  powershell -ExecutionPolicy Bypass -File scripts\lan-firewall.ps1 -Address 192.168.1.10 -Devices 192.168.1.23
  powershell -ExecutionPolicy Bypass -File scripts\lan-firewall.ps1 -Address 192.168.1.10 -Devices 192.168.1.23,192.168.1.31 -Interface Wi-Fi

The rule is limited to: inbound TCP on one port, to this PC's one address, from the listed device
addresses, on the Private profile, on one interface, for the Python interpreter that runs SignalDesk.
Give your phone a fixed address with a DHCP reservation on your router (not port forwarding), or the
rule stops matching when its address changes. No router port forwarding is needed or wanted.
#>
param(
    [Parameter(Mandatory)][string]$Address,
    [Parameter(Mandatory)][string[]]$Devices,
    [int]$Port = 8443,
    [string]$Interface = 'Wi-Fi'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$venv = Join-Path $repo '.venv\Scripts\python.exe'
# The venv launcher starts the base interpreter, which is the process that owns the socket.
$python = (& $venv -c "import sys; print(sys._base_executable)").Trim()
if (-not (Test-Path -LiteralPath $python)) { throw "Could not find the Python interpreter ($python)." }
$category = (Get-NetConnectionProfile -InterfaceAlias $Interface -ErrorAction Stop).NetworkCategory
if ($category -ne 'Private') { throw "The '$Interface' network is '$category', not Private. Set your home Wi-Fi to Private in Settings > Network & internet first." }

New-NetFirewallRule -DisplayName "SignalDesk HTTPS (LAN, port $Port)" -Group 'SignalDesk' -Direction Inbound -Action Allow -Protocol TCP `
    -LocalPort $Port -LocalAddress $Address -RemoteAddress $Devices -Profile Private -InterfaceAlias $Interface -Program $python `
    -Description 'Created by scripts\lan-firewall.ps1. Remove with scripts\lan-firewall-remove.ps1.' | Out-Null
Write-Output "Allowed $($Devices -join ', ') to reach https://$Address`:$Port on '$Interface' (Private) for $python."
Write-Output 'Nothing else is opened: the app on 127.0.0.1:8780 and Colibri on 127.0.0.1:8000 are loopback-only.'
