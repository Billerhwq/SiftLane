param(
    [string]$Tag = "",
    [string]$PythonExecutable = "python",
    [string]$NodeExecutable = "node",
    [string]$NpmCli = "",
    [switch]$Install,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$engineRoot = Join-Path $repoRoot "engine"
$webRoot = Join-Path $repoRoot "apps\web"
$artifactsRoot = Join-Path $repoRoot "release-artifacts"
$venvPython = Join-Path $engineRoot ".venv\Scripts\python.exe"

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Npm([string[]]$Arguments) {
    if ($NpmCli) {
        & $NodeExecutable $NpmCli @Arguments
    }
    else {
        & npm @Arguments
    }
    Assert-ExitCode "npm $($Arguments -join ' ')"
}

& $NodeExecutable -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22 ? 0 : 1)"
Assert-ExitCode "Node.js 20.19+ or 22.12+ version check"
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
    Assert-ExitCode "Install engine build dependencies"

    Push-Location $webRoot
    try {
        Invoke-Npm @("ci")
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

& (Join-Path $PSScriptRoot "check-release.ps1") -Tag $Tag -PythonExecutable $venvPython
Assert-ExitCode "Release metadata check"

$gitStatus = @(& git status --porcelain --untracked-files=all)
Assert-ExitCode "Read Git worktree status"
$isDirty = $gitStatus.Count -gt 0
if ($isDirty -and -not $AllowDirty) {
    throw "Release packaging requires a clean worktree. Use -AllowDirty only for a local candidate exercise."
}

if ((Split-Path -Parent $artifactsRoot) -ne $repoRoot) {
    throw "Refusing to prepare an unexpected artifact path: $artifactsRoot"
}
if (Test-Path -LiteralPath $artifactsRoot) {
    Remove-Item -LiteralPath $artifactsRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $artifactsRoot | Out-Null

$version = (Get-Content -Raw (Join-Path $repoRoot "VERSION")).Trim()
& $venvPython -m build --sdist --wheel --no-isolation --outdir $artifactsRoot $engineRoot
Assert-ExitCode "Build Python release artifacts"

Push-Location $webRoot
try {
    Invoke-Npm @("run", "build")
}
finally {
    Pop-Location
}

$webArchive = Join-Path $artifactsRoot "siftlane-web-$version.zip"
Compress-Archive -Path (Join-Path $webRoot "dist\*") -DestinationPath $webArchive -CompressionLevel Optimal

$wheel = Get-ChildItem -LiteralPath $artifactsRoot -Filter "*.whl" | Select-Object -First 1
if (-not $wheel) {
    throw "Python wheel was not produced"
}
$smokeVenv = Join-Path $artifactsRoot ".wheel-smoke"
$webSmoke = Join-Path $artifactsRoot ".web-smoke"
try {
    & $venvPython -m venv $smokeVenv
    Assert-ExitCode "Create wheel smoke-test environment"
    $smokePython = Join-Path $smokeVenv "Scripts\python.exe"
    & $smokePython -m pip install --no-deps $wheel.FullName
    Assert-ExitCode "Install release wheel"
    & $smokePython -c "import siftlane_engine; assert siftlane_engine.__version__ == '$version'"
    Assert-ExitCode "Import release wheel"

    Expand-Archive -LiteralPath $webArchive -DestinationPath $webSmoke
    if (-not (Test-Path -LiteralPath (Join-Path $webSmoke "index.html"))) {
        throw "Web release archive does not contain index.html"
    }
}
finally {
    if (Test-Path -LiteralPath $smokeVenv) {
        Remove-Item -LiteralPath $smokeVenv -Recurse -Force
    }
    if (Test-Path -LiteralPath $webSmoke) {
        Remove-Item -LiteralPath $webSmoke -Recurse -Force
    }
}

$commit = (& git rev-parse HEAD).Trim()
Assert-ExitCode "Read Git commit"
$distributables = Get-ChildItem -LiteralPath $artifactsRoot -File | Sort-Object Name
$manifestArtifacts = @($distributables | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    [ordered]@{
        name = $_.Name
        bytes = $_.Length
        sha256 = $hash.Hash.ToLowerInvariant()
    }
})
$manifest = [ordered]@{
    product = "Siftlane"
    version = $version
    tag = $Tag
    gitCommit = $commit
    gitDirty = $isDirty
    createdAt = (Get-Date).ToUniversalTime().ToString("o")
    artifacts = $manifestArtifacts
}
$manifestPath = Join-Path $artifactsRoot "manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$checksumLines = Get-ChildItem -LiteralPath $artifactsRoot -File |
    Where-Object Name -ne "SHA256SUMS.txt" |
    Sort-Object Name |
    ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        "$($hash.Hash.ToLowerInvariant())  $($_.Name)"
    }
$checksumLines | Set-Content -LiteralPath (Join-Path $artifactsRoot "SHA256SUMS.txt") -Encoding ASCII

& $venvPython (Join-Path $engineRoot "scripts\security_audit.py") --repo-root $repoRoot --artifacts-dir $artifactsRoot
Assert-ExitCode "Release artifact security audit"

Write-Host "Release artifacts passed smoke checks: $artifactsRoot"
Get-ChildItem -LiteralPath $artifactsRoot -File | Sort-Object Name | Select-Object Name, Length
