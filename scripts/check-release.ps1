param(
    [string]$ExpectedVersion = "",
    [string]$Tag = "",
    [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$engineRoot = Join-Path $repoRoot "engine"
$webRoot = Join-Path $repoRoot "apps\web"
$venvPython = Join-Path $engineRoot ".venv\Scripts\python.exe"

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Assert-Equal([string]$Name, [string]$Actual, [string]$Expected) {
    if ($Actual -ne $Expected) {
        throw "$Name is '$Actual'; expected '$Expected'"
    }
}

$version = (Get-Content -Raw (Join-Path $repoRoot "VERSION")).Trim()
if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z.-]+)?$') {
    throw "VERSION is not a supported semantic version: '$version'"
}
if ($ExpectedVersion) {
    Assert-Equal "VERSION" $version $ExpectedVersion
}
if ($Tag) {
    Assert-Equal "Release tag" $Tag "v$version"
}

if (-not $PythonExecutable) {
    $PythonExecutable = if (Test-Path -LiteralPath $venvPython) {
        $venvPython
    }
    else {
        "python"
    }
}

$webPackagePath = Join-Path $webRoot "package.json"
$webLockPath = Join-Path $webRoot "package-lock.json"
$webVersions = @(& $PythonExecutable -c "import json, pathlib; package=json.loads(pathlib.Path(r'$webPackagePath').read_text(encoding='utf-8')); lock=json.loads(pathlib.Path(r'$webLockPath').read_text(encoding='utf-8')); print(package['version']); print(lock['version']); print(lock['packages']['']['version'])")
Assert-ExitCode "Read Web package versions"
Assert-Equal "Web package version" $webVersions[0] $version
Assert-Equal "Web lockfile version" $webVersions[1] $version
Assert-Equal "Web lockfile root package version" $webVersions[2] $version

$pyprojectPath = Join-Path $engineRoot "pyproject.toml"
$pyprojectVersion = (& $PythonExecutable -c "import pathlib, tomllib; print(tomllib.loads(pathlib.Path(r'$pyprojectPath').read_text(encoding='utf-8'))['project']['version'])").Trim()
Assert-ExitCode "Read Python project version"
Assert-Equal "Python project version" $pyprojectVersion $version

$engineSource = Join-Path $engineRoot "src"
$runtimeVersion = (& $PythonExecutable -c "import sys; sys.path.insert(0, r'$engineSource'); import siftlane_engine; print(siftlane_engine.__version__)").Trim()
Assert-ExitCode "Read Python runtime version"
Assert-Equal "Python runtime version" $runtimeVersion $version

$requiredPaths = @(
    "ACCEPTANCE.md",
    "PRD-P2-release-hardening.md",
    "documentation\release.md",
    "documentation\releases\v$version.md",
    ".github\workflows\ci.yml",
    ".github\workflows\release.yml",
    "outputs\p1-desktop.png",
    "outputs\p1-desktop-results.png",
    "outputs\p1-mobile.png",
    "outputs\p2-branch-retry.png",
    "outputs\p2-scheduler.png"
)
foreach ($relativePath in $requiredPaths) {
    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $relativePath))) {
        throw "Required release evidence is missing: $relativePath"
    }
}

Write-Host "Release metadata passed for Siftlane $version"
