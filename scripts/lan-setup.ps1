<#
Opt-in: create a trusted HTTPS certificate for SignalDesk's LAN entry point. Run it yourself.

Uses mkcert (https://github.com/FiloSottile/mkcert), an established tool for a private local CA.
Install it first:   winget install FiloSottile.mkcert

  powershell -ExecutionPolicy Bypass -File scripts\lan-setup.ps1 -Address 192.168.1.10
  powershell -ExecutionPolicy Bypass -File scripts\lan-setup.ps1 -Address 192.168.1.10 -Names hemant-pc.local

What it changes:
  * mkcert -install adds mkcert's root CA to YOUR Windows user trust store (Edge on this PC trusts it).
  * Creates <data dir>\tls\signaldesk.pem (certificate) and signaldesk-key.pem (private key), the key
    readable only by you.
  * Copies the PUBLIC root CA certificate to <data dir>\tls\SignalDesk-local-CA.crt for your phone.
The root CA's PRIVATE key stays in mkcert's folder (mkcert -CAROOT). Anyone with that file can create
certificates your PC and phone trust, so keep it private; see docs\LAN_AND_PANEL.md for moving it offline.
Undo with scripts\lan-undo.ps1.
#>
param(
    [Parameter(Mandatory)][string]$Address,
    [string[]]$Names = @(),
    [string]$DataDir = 'D:\LocalAI\signaldesk'
)
$ErrorActionPreference = 'Stop'
$ip = $null
if (-not [System.Net.IPAddress]::TryParse($Address, [ref]$ip) -or $ip.AddressFamily -ne 'InterNetwork') { throw "Give this PC's IPv4 Wi-Fi address, e.g. 192.168.1.10." }
$b = $ip.GetAddressBytes()
$private = ($b[0] -eq 10) -or ($b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31) -or ($b[0] -eq 192 -and $b[1] -eq 168)
if (-not $private) { throw "$Address is not a private home-network address. Refusing." }
$mkcert = Get-Command mkcert -ErrorAction SilentlyContinue
if (-not $mkcert) { throw 'mkcert is not installed. Run: winget install FiloSottile.mkcert   then open a new PowerShell window.' }

$tls = Join-Path $DataDir 'tls'
New-Item -ItemType Directory -Force -Path $tls | Out-Null
& mkcert -install
$cert = Join-Path $tls 'signaldesk.pem'
$key = Join-Path $tls 'signaldesk-key.pem'
& mkcert -cert-file $cert -key-file $key $Address @Names
if ($LASTEXITCODE -ne 0) { throw 'mkcert could not create the certificate.' }
$caroot = (& mkcert -CAROOT).Trim()
Copy-Item -LiteralPath (Join-Path $caroot 'rootCA.pem') -Destination (Join-Path $tls 'SignalDesk-local-CA.crt') -Force
# Only you can read or replace the private key.
& icacls $key /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null

$hosts = (@($Address) + $Names | ForEach-Object { "`"$_`"" }) -join ', '
Write-Output ''
Write-Output "Certificate: $cert"
Write-Output "Private key: $key (readable only by $env:USERNAME)"
Write-Output "Phone certificate (public): $(Join-Path $tls 'SignalDesk-local-CA.crt')"
Write-Output "Root CA private key (keep private): $(Join-Path $caroot 'rootCA-key.pem')"
Write-Output ''
Write-Output "Add this to $DataDir\config.toml:"
Write-Output '[lan]'
Write-Output 'enabled = false            # start LAN mode with --lan, or set true'
Write-Output "bind = `"$Address`""
Write-Output 'port = 8443'
Write-Output "hostnames = [$hosts]"
Write-Output "cert_file = '$cert'"
Write-Output "key_file = '$key'"
