param(
    [switch]$SkipBackendInstall,
    [switch]$SkipFrontendInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"
$DataDir = Join-Path $RepoRoot "data"
$RuntimeConfig = Join-Path $FrontendDir "public\runtime-config.json"
$RuntimeExample = Join-Path $FrontendDir "public\runtime-config.example.json"

function Write-Step($Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-CheckedNative($File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$File failed with exit code $LASTEXITCODE"
    }
}

function Get-CompatiblePython {
    if (Test-Command "py") {
        $Installed = (& py -0p 2>$null) -join "`n"
        foreach ($Version in @("3.13", "3.12", "3.11")) {
            if ($Installed -match [regex]::Escape("-V:$Version")) {
                return @{ Command = "py"; Args = @("-$Version") }
            }
        }
    }
    foreach ($Command in @("python", "python3")) {
        if (Test-Command $Command) {
            $VersionOutput = & $Command -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ($LASTEXITCODE -eq 0 -and $VersionOutput -match "^(3)\.(11|12|13)$") {
                return @{ Command = $Command; Args = @() }
            }
        }
    }
    $Detected = ""
    if (Test-Command "python") {
        $Detected = (& python --version 2>&1) -join " "
    } elseif (Test-Command "py") {
        $Detected = (& py -0p 2>&1) -join " "
    }
    throw "Python 3.11/3.12/3.13 is required. Python 3.14 is not currently supported by pinned backend dependencies. Detected: $Detected"
}

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

function Invoke-SystemPython($Arguments) {
    $Python = Get-CompatiblePython
    & $Python.Command @($Python.Args + $Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

function Test-CompatiblePythonExecutable($PythonExe) {
    if (!(Test-Path $PythonExe)) {
        return $false
    }
    & $PythonExe -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3, 11), (3, 12), (3, 13)] else 1)" *> $null
    return $LASTEXITCODE -eq 0
}

Write-Step "Checking required tools"
if (!(Test-Command "node")) {
    throw "Node.js not found. Please install Node.js 20+ and add it to PATH."
}
if (!(Test-Command "npm")) {
    throw "npm not found. Please install Node.js/npm and add it to PATH."
}
Invoke-SystemPython @("--version")
Invoke-CheckedNative "node" @("--version")
Invoke-CheckedNative "npm" @("--version")

if (!(Test-Command "psql")) {
    Write-Warning "psql not found. PostgreSQL may not be installed or not in PATH. Install PostgreSQL 15+ for local database development."
} else {
    Invoke-CheckedNative "psql" @("--version")
}

Write-Step "Preparing .env"
if (!(Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "Created .env from .env.example. Edit DATABASE_URL, AMAP_WEB_SERVICE_KEY and DEEPSEEK_API_KEY as needed."
} else {
    Write-Host ".env already exists; keeping existing values."
}
Import-DotEnv $EnvFile

Write-Step "Preparing data directory"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
if (!(Test-Path (Join-Path $DataDir "site_feedback.json"))) {
    "[]" | Set-Content -Path (Join-Path $DataDir "site_feedback.json") -Encoding UTF8
}
if (!(Test-Path (Join-Path $DataDir "agent_traces.json"))) {
    "{}" | Set-Content -Path (Join-Path $DataDir "agent_traces.json") -Encoding UTF8
}

Write-Step "Preparing frontend runtime config"
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
    Write-Host "Created frontend/public/runtime-config.json. It is ignored by git."
} else {
    Write-Host "frontend/public/runtime-config.json already exists; keeping existing values."
}

if (!$SkipBackendInstall) {
    Write-Step "Preparing backend virtual environment"
    $VenvDir = Join-Path $BackendDir ".venv"
    $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
    if ((Test-Path $VenvPython) -and !(Test-CompatiblePythonExecutable $VenvPython)) {
        Write-Warning "Existing backend/.venv uses an unsupported Python version. Recreating it."
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }
    if (!(Test-Path $VenvPython)) {
        Invoke-SystemPython @("-m", "venv", $VenvDir)
    }
    Invoke-CheckedNative $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
    Invoke-CheckedNative $VenvPython @("-m", "pip", "install", "-r", (Join-Path $BackendDir "requirements.txt"))
}

if (!$SkipFrontendInstall) {
    Write-Step "Installing frontend dependencies"
    Push-Location $FrontendDir
    try {
        Invoke-CheckedNative "npm" @("install")
    } finally {
        Pop-Location
    }
}

Write-Host ""
Write-Host "Windows development environment is ready." -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Edit .env and frontend/public/runtime-config.json if keys or database URL are missing."
Write-Host "  2. Start backend:  powershell -ExecutionPolicy Bypass -File scripts/windows/start_backend.ps1"
Write-Host "  3. Start frontend: powershell -ExecutionPolicy Bypass -File scripts/windows/start_frontend.ps1"
Write-Host "  4. Open browser:   http://localhost:5173"
