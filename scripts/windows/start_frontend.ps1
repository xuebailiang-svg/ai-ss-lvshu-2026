param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$FrontendDir = Join-Path $RepoRoot "frontend"
$EnvFile = Join-Path $RepoRoot ".env"
$RuntimeConfig = Join-Path $FrontendDir "public\runtime-config.json"
$RuntimeExample = Join-Path $FrontendDir "public\runtime-config.example.json"

function Import-DotEnv($Path) {
    if (!(Test-Path $Path)) {
        return
    }
    Get-Content $Path | ForEach-Object {
        $Line = $_.Trim()
        if (!$Line -or $Line.StartsWith("#")) {
            return
        }
        $Index = $Line.IndexOf("=")
        if ($Index -le 0) {
            return
        }
        $Key = $Line.Substring(0, $Index).Trim()
        $Value = $Line.Substring($Index + 1).Trim()
        if (($Value.StartsWith('"') -and $Value.EndsWith('"')) -or ($Value.StartsWith("'") -and $Value.EndsWith("'"))) {
            $Value = $Value.Substring(1, $Value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($Key, $Value, "Process")
    }
}

function Invoke-CheckedNative($File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$File failed with exit code $LASTEXITCODE"
    }
}

Import-DotEnv $EnvFile

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RuntimeConfig) | Out-Null
if (!(Test-Path $RuntimeConfig)) {
    if (Test-Path $RuntimeExample) {
        Copy-Item $RuntimeExample $RuntimeConfig
    }
    $AmapJsKey = [Environment]::GetEnvironmentVariable("VITE_AMAP_JS_KEY", "Process")
    $AmapSecurityJsCode = [Environment]::GetEnvironmentVariable("VITE_AMAP_SECURITY_JS_CODE", "Process")
    $MapProvider = [Environment]::GetEnvironmentVariable("MAP_PROVIDER", "Process")
    if (!$MapProvider) {
        $MapProvider = "amap"
    }
    $Runtime = [ordered]@{
        apiBaseUrl = "/api"
        amapJsKey = "$AmapJsKey"
        amapSecurityJsCode = "$AmapSecurityJsCode"
        mapProvider = "$MapProvider"
    }
    $Runtime | ConvertTo-Json -Depth 3 | Set-Content -Path $RuntimeConfig -Encoding UTF8
    Write-Host "Created frontend/public/runtime-config.json from .env values. Edit it if map config is missing."
}

Push-Location $FrontendDir
try {
    if (!$SkipInstall -and !(Test-Path "node_modules")) {
        Invoke-CheckedNative "npm" @("install")
    }
    Write-Host "Starting Vite frontend at http://localhost:5173" -ForegroundColor Green
    & npm run dev
    if ($LASTEXITCODE -ne 0) {
        throw "npm run dev failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
