<#
Read-only: where SignalDesk keeps data and whether those volumes are encrypted. Changes nothing.
  powershell -ExecutionPolicy Bypass -File scripts\check-storage.ps1
For more detail, run in an elevated PowerShell:  manage-bde -status C:   and   manage-bde -status D:
#>
param([string]$DataDir = 'D:\LocalAI\signaldesk')
$paths = [ordered]@{
    'Database (+ -wal, -shm)'               = Join-Path $DataDir 'signaldesk.db'
    'Profile (your CV facts)'               = Join-Path $DataDir 'profile.json'
    'Sign-in password hash'                 = Join-Path $DataDir 'auth.json'
    'Cloud keys (Supabase secret)'          = Join-Path $DataDir 'delivery.env'
    'Privacy-check logins'                  = Join-Path $DataDir 'rls-test.env'
    'LAN certificate and private key'       = Join-Path $DataDir 'tls'
    'Logs'                                  = Join-Path $DataDir 'logs'
    'Saved briefings (Markdown)'            = Join-Path $DataDir 'digests'
    'Evaluation outputs'                    = Join-Path $DataDir 'evals'
    'Backup from the V2 upgrade'            = Join-Path $DataDir 'backup-before-v2'
    'SQLite temporary files'                = $env:TEMP
    'mkcert root CA (private key)'          = Join-Path $env:LOCALAPPDATA 'mkcert'
    'Edge profile (side-panel token)'       = Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data'
    'Android signing key'                   = Join-Path $env:USERPROFILE '.android\debug.keystore'
    'Phone app installer (public key only)' = Join-Path $env:USERPROFILE 'Downloads\SignalDesk-reader.apk'
}
foreach ($k in $paths.Keys) {
    $p = $paths[$k]
    $state = if (Test-Path -LiteralPath $p) { 'present' } else { 'absent' }
    '{0,-40} {1,-8} {2}' -f $k, $state, $p
}
''
'Volume encryption (BitLocker / Device encryption):'
$names = @{ 0 = 'cannot be encrypted'; 1 = 'ON'; 2 = 'OFF'; 3 = 'encrypting'; 4 = 'decrypting'; 5 = 'suspended'; 6 = 'ON (locked)'; 8 = 'waiting for activation' }
foreach ($v in ($paths.Values | ForEach-Object { (Split-Path -Qualifier $_) } | Sort-Object -Unique)) {
    try {
        $val = (New-Object -ComObject Shell.Application).NameSpace("$v\").Self.ExtendedProperty('System.Volume.BitLockerProtection')
        $label = if ($null -eq $val) { 'unknown (run manage-bde -status as administrator)' } else { $names[[int]$val] }
        '{0}  {1}' -f $v, $label
    } catch { '{0}  could not read: {1}' -f $v, $_.Exception.Message }
}
''
'Who can read the secret files:'
foreach ($f in @('auth.json', 'delivery.env', 'rls-test.env', 'tls\signaldesk-key.pem')) {
    $p = Join-Path $DataDir $f
    if (Test-Path -LiteralPath $p) { "--- $p"; icacls $p }
}
