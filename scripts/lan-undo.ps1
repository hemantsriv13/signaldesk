<#
Undo LAN setup on this PC. Run the firewall removal separately (it needs administrator rights):
  powershell -ExecutionPolicy Bypass -File scripts\lan-firewall-remove.ps1     (elevated)
  powershell -ExecutionPolicy Bypass -File scripts\lan-undo.ps1

This script:
  * removes mkcert's root CA from your Windows trust store (mkcert -uninstall),
  * deletes <data dir>\tls (certificate, key, phone copy of the CA certificate) after you confirm,
  * signs out every LAN session and revokes every side-panel token.
It does not touch your data. Then: set [lan] enabled = false (or remove [lan]) in config.toml, and on
your phone remove the "mkcert" CA under Settings > Security > Encryption & credentials > User credentials.
mkcert's own folder (mkcert -CAROOT) with the root CA private key is left for you to delete.
#>
param([string]$DataDir = 'D:\LocalAI\signaldesk')
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (Get-Command mkcert -ErrorAction SilentlyContinue) { & mkcert -uninstall } else { Write-Output 'mkcert not found; remove the "mkcert" root from certmgr.msc > Trusted Root Certification Authorities if it is there.' }
$tls = Join-Path $DataDir 'tls'
if (Test-Path -LiteralPath $tls) {
    $answer = Read-Host "Delete $tls (certificate and private key)? Type yes"
    if ($answer -eq 'yes') { Remove-Item -LiteralPath $tls -Recurse -Force; Write-Output "Deleted $tls." } else { Write-Output 'Kept.' }
}
& (Join-Path $repo '.venv\Scripts\python.exe') -m signaldesk auth revoke-sessions --home $DataDir
& (Join-Path $repo '.venv\Scripts\python.exe') -m signaldesk auth revoke-panel --home $DataDir
Write-Output "Done. mkcert's root CA folder: run 'mkcert -CAROOT' to find it and delete it if you no longer need it."
