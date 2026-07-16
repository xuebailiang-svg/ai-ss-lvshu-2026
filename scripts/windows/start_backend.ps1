param(
    [int]$Port = 8000,
    [string]$HostName = "127.0.0.1",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackendDir = Join-Path $RepoRoot "backend"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"
$DataDir = Join-Path $RepoRoot "data"
$RuntimeConfig = Join-Path $RepoRoot "frontend\public\runtime-config.json"

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

if (!(Test-Path $EnvFile)) {
    Copy-Item $EnvExample $EnvFile
    Write-Warning "Created .env from .env.example. Edit DATABASE_URL and API keys before real debugging."
}
Import-DotEnv $EnvFile

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
if (!(Test-Path (Join-Path $DataDir "site_feedback.json"))) {
    "[]" | Set-Content -Path (Join-Path $DataDir "site_feedback.json") -Encoding UTF8
}
if (!(Test-Path (Join-Path $DataDir "agent_traces.json"))) {
    "{}" | Set-Content -Path (Join-Path $DataDir "agent_traces.json") -Encoding UTF8
}

if (![Environment]::GetEnvironmentVariable("APP_ENV", "Process")) {
    [Environment]::SetEnvironmentVariable("APP_ENV", "development", "Process")
}
if (![Environment]::GetEnvironmentVariable("SITE_FEEDBACK_STORE_PATH", "Process")) {
    [Environment]::SetEnvironmentVariable("SITE_FEEDBACK_STORE_PATH", "data/site_feedback.json", "Process")
}
if (![Environment]::GetEnvironmentVariable("AGENT_TRACE_STORE_PATH", "Process")) {
    [Environment]::SetEnvironmentVariable("AGENT_TRACE_STORE_PATH", "data/agent_traces.json", "Process")
}
if (![Environment]::GetEnvironmentVariable("FRONTEND_RUNTIME_CONFIG_PATH", "Process")) {
    [Environment]::SetEnvironmentVariable("FRONTEND_RUNTIME_CONFIG_PATH", $RuntimeConfig, "Process")
}

$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if ((Test-Path $VenvPython) -and !(Test-CompatiblePythonExecutable $VenvPython)) {
    Write-Warning "Existing backend/.venv uses an unsupported Python version. Recreating it."
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
}
if (!(Test-Path $VenvPython)) {
    Invoke-SystemPython @("-m", "venv", $VenvDir)
}

if (!$SkipInstall) {
    Invoke-CheckedNative $VenvPython @("-m", "pip", "install", "-r", (Join-Path $BackendDir "requirements.txt"))
}

Write-Host "Starting FastAPI backend at http://$HostName`:$Port" -ForegroundColor Green
Push-Location $BackendDir
try {
    & $VenvPython -m uvicorn app.main:app --host $HostName --port $Port --reload
    if ($LASTEXITCODE -ne 0) {
        throw "uvicorn failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}
