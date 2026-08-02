param(
    [string]$PythonExecutable = "python",
    [string]$NodeExecutable = "node",
    [string]$PlaywrightNodeExecutable = "",
    [string]$NpmCli = "",
    [string]$BrowserChannel = "",
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$engineRoot = Join-Path $repoRoot "engine"
$webRoot = Join-Path $repoRoot "apps\web"
$venvPython = Join-Path $engineRoot ".venv\Scripts\python.exe"
if (-not $PlaywrightNodeExecutable) {
    $PlaywrightNodeExecutable = $NodeExecutable
}

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

& $NodeExecutable -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22 ? 0 : 1)"
Assert-ExitCode "Node.js 20.19+ or 22.12+ version check"
& $PlaywrightNodeExecutable -e "process.exit(Number(process.versions.node.split('.')[0]) >= 18 ? 0 : 1)"
Assert-ExitCode "Playwright Node.js 18+ version check"
if (Test-Path -LiteralPath $NodeExecutable) {
    $nodeDirectory = Split-Path -Parent (Resolve-Path -LiteralPath $NodeExecutable)
    $env:PATH = "$nodeDirectory;$env:PATH"
}

if ($Install) {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        & $PythonExecutable -m venv (Join-Path $engineRoot ".venv")
        Assert-ExitCode "Create Python virtual environment"
    }
    & $venvPython -m pip install --upgrade "pip>=26.1.2"
    Assert-ExitCode "Upgrade Python package installer"
    & $venvPython -m pip install -e "$engineRoot[test]"
    Assert-ExitCode "Install engine dependencies"

    Push-Location $webRoot
    try {
        if ($NpmCli) {
            & $NodeExecutable $NpmCli ci
        }
        else {
            & npm ci
        }
        Assert-ExitCode "Install web dependencies"
        if (-not $BrowserChannel) {
            & $PlaywrightNodeExecutable (Join-Path $webRoot "tests\run-playwright.mjs") install chromium
            Assert-ExitCode "Install Playwright Chromium"
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Engine virtual environment is missing. Run this script with -Install."
}
if (-not (Test-Path -LiteralPath (Join-Path $webRoot "node_modules"))) {
    throw "Web dependencies are missing. Run this script with -Install."
}

Push-Location $engineRoot
try {
    & $venvPython -m pytest -q
    Assert-ExitCode "Engine test suite"
}
finally {
    Pop-Location
}

$env:SIFTLANE_E2E_PYTHON = $venvPython
$env:SIFTLANE_E2E_BROWSER_CHANNEL = $BrowserChannel
$env:SIFTLANE_E2E_VITE_NODE = $NodeExecutable
Push-Location $webRoot
try {
    if ($NpmCli) {
        & $NodeExecutable $NpmCli run build
    }
    else {
        & npm run build
    }
    Assert-ExitCode "Web production build"
    & $PlaywrightNodeExecutable (Join-Path $webRoot "tests\run-playwright.mjs") test
    Assert-ExitCode "Web end-to-end suite"
}
finally {
    Pop-Location
}

$version = (Get-Content -Raw (Join-Path $repoRoot "VERSION")).Trim()
$versionParts = $version.Split("-")[0].Split(".") | ForEach-Object { [int]$_ }
if ($versionParts[0] -ge 1) {
    & (Join-Path $PSScriptRoot "p5-qualification.ps1") -PythonExecutable $venvPython -SoakDurationSeconds 30
    Assert-ExitCode "P5 capacity, backup and soak qualification"

    $securityArguments = @{
        PythonExecutable = $venvPython
        NodeExecutable = $NodeExecutable
        NpmCli = $NpmCli
    }
    & (Join-Path $PSScriptRoot "security-check.ps1") @securityArguments
    Assert-ExitCode "P5 security checks"
}

& (Join-Path $PSScriptRoot "check-release.ps1") -PythonExecutable $venvPython
Assert-ExitCode "Release metadata check"

Write-Host "Siftlane lifecycle acceptance and release metadata gates passed."
