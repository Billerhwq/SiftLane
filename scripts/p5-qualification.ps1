param(
    [string]$PythonExecutable = "python",
    [double]$SoakDurationSeconds = 30
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$engineRoot = Join-Path $repoRoot "engine"
$outputsRoot = Join-Path $repoRoot "outputs"
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("siftlane-p5-" + [guid]::NewGuid().ToString("N"))

function Assert-ExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
try {
    & $PythonExecutable (Join-Path $engineRoot "scripts\capacity_test.py") `
        --data-dir (Join-Path $temporaryRoot "capacity") `
        --output (Join-Path $outputsRoot "p5-capacity-report.json") `
        --runs 120 --items-per-run 20 --concurrency 8 `
        --max-seconds 75 --max-database-bytes 67108864
    Assert-ExitCode "P5 capacity qualification"

    & $PythonExecutable (Join-Path $engineRoot "scripts\backup_drill.py") `
        --data-dir (Join-Path $temporaryRoot "capacity") `
        --work-dir (Join-Path $temporaryRoot "backup-drill") `
        --output (Join-Path $outputsRoot "p5-backup-restore-report.json") `
        --max-rto-seconds 60
    Assert-ExitCode "P5 backup and restore drill"

    & $PythonExecutable (Join-Path $engineRoot "scripts\soak_test.py") `
        --data-dir (Join-Path $temporaryRoot "soak") `
        --output (Join-Path $outputsRoot "p5-soak-report.json") `
        --duration-seconds $SoakDurationSeconds --interval-seconds 0.25 `
        --items-per-cycle 5 --max-heap-growth-bytes 33554432 `
        --max-peak-heap-bytes 134217728
    Assert-ExitCode "P5 soak qualification"
}
finally {
    $resolvedTemporary = [IO.Path]::GetFullPath($temporaryRoot)
    $resolvedSystemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedTemporary.StartsWith($resolvedSystemTemp) -and (Test-Path -LiteralPath $resolvedTemporary)) {
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}

Write-Host "P5 capacity and soak qualification passed."
