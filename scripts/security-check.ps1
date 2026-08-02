param(
    [string]$PythonExecutable = "python",
    [string]$NodeExecutable = "node",
    [string]$NpmCli = "",
    [string]$ArtifactsDirectory = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$engineRoot = Join-Path $repoRoot "engine"
$webRoot = Join-Path $repoRoot "apps\web"

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

& $PythonExecutable -m pip check
Assert-ExitCode "Python dependency consistency"
& $PythonExecutable -m pip_audit $engineRoot --strict --progress-spinner off
Assert-ExitCode "Python vulnerability audit"

Push-Location $webRoot
try {
    if ($NpmCli) {
        & $NodeExecutable $NpmCli audit --omit=dev --audit-level=high --registry=https://registry.npmjs.org
    }
    else {
        & npm audit --omit=dev --audit-level=high --registry=https://registry.npmjs.org
    }
    Assert-ExitCode "Web production dependency audit"
}
finally {
    Pop-Location
}

$auditArguments = @("--repo-root", $repoRoot)
if ($ArtifactsDirectory) {
    $auditArguments += @("--artifacts-dir", $ArtifactsDirectory)
}
& $PythonExecutable (Join-Path $engineRoot "scripts\security_audit.py") @auditArguments
Assert-ExitCode "Credential and artifact audit"

Write-Host "P5 security checks passed."
