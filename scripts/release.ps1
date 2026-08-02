param(
    [string]$Tag = "",
    [string]$PythonExecutable = "python",
    [string]$NodeExecutable = "node",
    [string]$PlaywrightNodeExecutable = "",
    [string]$NpmCli = "",
    [string]$BrowserChannel = "",
    [switch]$Install,
    [switch]$AllowDirty
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Tag) {
    $Tag = "v$((Get-Content -Raw (Join-Path $repoRoot 'VERSION')).Trim())"
}

$verifyArguments = @{
    PythonExecutable = $PythonExecutable
    NodeExecutable = $NodeExecutable
    PlaywrightNodeExecutable = $PlaywrightNodeExecutable
    NpmCli = $NpmCli
    BrowserChannel = $BrowserChannel
}
if ($Install) {
    $verifyArguments.Install = $true
}
& (Join-Path $PSScriptRoot "verify.ps1") @verifyArguments
if ($LASTEXITCODE -ne 0) {
    throw "Lifecycle acceptance failed with exit code $LASTEXITCODE"
}

$packageArguments = @{
    Tag = $Tag
    PythonExecutable = $PythonExecutable
    NodeExecutable = $NodeExecutable
    NpmCli = $NpmCli
}
if ($AllowDirty) {
    $packageArguments.AllowDirty = $true
}
& (Join-Path $PSScriptRoot "package-release.ps1") @packageArguments
if ($LASTEXITCODE -ne 0) {
    throw "Release packaging failed with exit code $LASTEXITCODE"
}

Write-Host "Siftlane $Tag release candidate passed the complete local gate."
