param(
    [int]$BridgePort = 8001,
    [int]$ErpPort = 8088,
    [string]$InitFile = ""
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BridgeDir = Join-Path $RootDir "services\axisstream-bridge"
$ErpDir = Join-Path $RootDir "services\erp-platform"
$PyExe = Join-Path $BridgeDir ".venv\Scripts\python.exe"
$ErpExe = Join-Path $ErpDir "erp-server.exe"

if (-not (Test-Path $PyExe)) {
    throw "Python venv not found at $PyExe"
}
if (-not (Test-Path $ErpExe)) {
    throw "ERP binary not found at $ErpExe"
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  AxisTech ISO ERP Platform Launcher (Encrypted Zero-Secret Mode)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

$resolvedInit = if ($InitFile) { $InitFile } else { Join-Path $RootDir "init.js" }
$syncInterval = "15"
$axisMode = "live"
$axisAuthMode = "cookie"
$rateLimitRpm = "300"
$requireApiKey = "false"

if (Test-Path $resolvedInit) {
    $rawInit = Get-Content -Path $resolvedInit -Raw -Encoding UTF8
    $cleanLines = ($rawInit -split "`r?`n" | Where-Object { $_ -notmatch '^\s*//' }) -join "`n"
    $firstBrace = $cleanLines.IndexOf('{')
    $lastBrace = $cleanLines.LastIndexOf('}')
    if ($firstBrace -lt 0 -or $lastBrace -le $firstBrace) {
        throw "Invalid init config format in $resolvedInit"
    }
    $jsonBody = $cleanLines.Substring($firstBrace, $lastBrace - $firstBrace + 1)
    $cfg = $jsonBody | ConvertFrom-Json

    if ($cfg.axisstream) {
        if (-not $env:AXISSTREAM_EMAIL -and $cfg.axisstream.email) { $env:AXISSTREAM_EMAIL = [string]$cfg.axisstream.email }
        if (-not $env:AXISSTREAM_PASSWORD -and $cfg.axisstream.password) { $env:AXISSTREAM_PASSWORD = [string]$cfg.axisstream.password }
        if ($cfg.axisstream.mode) { $axisMode = [string]$cfg.axisstream.mode }
        if ($cfg.axisstream.auth_mode) { $axisAuthMode = [string]$cfg.axisstream.auth_mode }
    }
    if ($cfg.security) {
        if (-not $env:AXISSTREAM_ENCRYPTION_KEY -and $cfg.security.encryption_key) {
            $env:AXISSTREAM_ENCRYPTION_KEY = [string]$cfg.security.encryption_key
        }
        if (-not $env:ERP_ENCRYPTION_KEY -and $cfg.security.encryption_key) {
            $env:ERP_ENCRYPTION_KEY = [string]$cfg.security.encryption_key
        }
        if ($null -ne $cfg.security.require_api_key) {
            $requireApiKey = if ($cfg.security.require_api_key) { "true" } else { "false" }
        }
        if ($cfg.security.rate_limit_rpm) {
            $rateLimitRpm = [string]$cfg.security.rate_limit_rpm
        }
    }
    if ($cfg.erp) {
        if (-not $PSBoundParameters.ContainsKey("BridgePort") -and $cfg.erp.bridge_port) { $BridgePort = [int]$cfg.erp.bridge_port }
        if (-not $PSBoundParameters.ContainsKey("ErpPort") -and $cfg.erp.erp_port) { $ErpPort = [int]$cfg.erp.erp_port }
        if ($cfg.erp.sync_interval_sec) { $syncInterval = [string]$cfg.erp.sync_interval_sec }
    }
    Write-Host "Loaded AxisTech & ISO 27001 config from init.js (secrets redacted)" -ForegroundColor Green
}

if (-not $env:AXISSTREAM_EMAIL) {
    $env:AXISSTREAM_EMAIL = Read-Host "AxisStream Email"
}
if (-not $env:AXISSTREAM_PASSWORD) {
    $secPwd = Read-Host "AxisStream Password" -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secPwd)
    try {
        $env:AXISSTREAM_PASSWORD = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$DataDir = Join-Path $RootDir "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
}
if (-not $env:AXISSTREAM_SQLITE_PATH) { $env:AXISSTREAM_SQLITE_PATH = Join-Path $DataDir "bridge_state.db" }
if (-not $env:ERP_DATA_FILE_PATH) { $env:ERP_DATA_FILE_PATH = Join-Path $DataDir "erp_state.json" }

if (-not $env:AXISSTREAM_ENCRYPTION_KEY) {
    $env:AXISSTREAM_ENCRYPTION_KEY = [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }))
}
if (-not $env:ERP_ENCRYPTION_KEY) {
    $env:ERP_ENCRYPTION_KEY = $env:AXISSTREAM_ENCRYPTION_KEY
}
if (-not $env:ERP_REQUIRE_API_KEY) { $env:ERP_REQUIRE_API_KEY = $requireApiKey }
if (-not $env:ERP_RATE_LIMIT_RPM) { $env:ERP_RATE_LIMIT_RPM = $rateLimitRpm }

$bridgeKey = if ($env:AXISSTREAM_INBOUND_API_KEY) { $env:AXISSTREAM_INBOUND_API_KEY } else { "local-live-bridge-key" }
if (-not $env:AXISSTREAM_MODE) { $env:AXISSTREAM_MODE = $axisMode }
if (-not $env:AXISSTREAM_AUTH_MODE) { $env:AXISSTREAM_AUTH_MODE = $axisAuthMode }
$env:AXISSTREAM_INBOUND_API_KEY = $bridgeKey
$env:PYTHONPATH = Join-Path $BridgeDir "src"
$env:ERP_PORT = "$ErpPort"
$env:BRIDGE_BASE_URL = "http://127.0.0.1:$BridgePort"
$env:BRIDGE_API_KEY = $bridgeKey
$env:SYNC_INTERVAL_SEC = $syncInterval

Write-Host "`n[1/3] Starting Python AxisTech Bridge (Encrypted Outbox, LIVE mode) on port $BridgePort..."
$bridgeProc = Start-Process -FilePath $PyExe `
    -ArgumentList "-m", "uvicorn", "axisstream_bridge.interfaces.api.app:app", "--host", "127.0.0.1", "--port", "$BridgePort" `
    -WorkingDirectory $BridgeDir -PassThru

try {
    Write-Host "[2/3] Waiting for live AxisStream login & initial workspace sync..."
    $synced = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if ($bridgeProc.HasExited) {
            throw "Python Bridge exited unexpectedly with code $($bridgeProc.ExitCode)"
        }
        try {
            $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$BridgePort/api/v1/projects" -Headers @{ "X-API-Key" = $bridgeKey } -TimeoutSec 3
            if ($resp.last_error) {
                throw "Live AxisStream sync failed: $($resp.last_error)"
            }
            if ($resp.count -ge 1) {
                Write-Host "      -> Synced $($resp.count) live AxisTech workspace(s)!" -ForegroundColor Green
                $synced = $true
                break
            }
        } catch {
            if ($_.Exception.Message -like "Live AxisStream sync failed:*") {
                throw $_
            }
        }
    }
    if (-not $synced) {
        throw "Timed out waiting for Python Bridge live sync on port $BridgePort"
    }

    Write-Host "[3/3] Starting Golang AxisTech ISO ERP (AES-256-GCM) on http://127.0.0.1:$ErpPort/ ..." -ForegroundColor Green
    Write-Host "      Press Ctrl+C to stop both services.`n"
    & $ErpExe
}
finally {
    Remove-Item Env:AXISSTREAM_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:AXISSTREAM_ENCRYPTION_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:ERP_ENCRYPTION_KEY -ErrorAction SilentlyContinue
    if ($bridgeProc -and -not $bridgeProc.HasExited) {
        Stop-Process -Id $bridgeProc.Id -Force -ErrorAction SilentlyContinue
    }
}
