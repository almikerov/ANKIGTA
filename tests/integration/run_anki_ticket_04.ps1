$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtime = Join-Path $repoRoot '.scratch\ticket-04-anki-integration-runtime'
$evidence = Join-Path $runtime 'evidence'
$primaryBase = Join-Path $runtime 'primary-base'
$presentCopyBase = Join-Path $runtime 'present-copy-base'
$restoreSourceBase = Join-Path $runtime 'restore-source-base'
$restorePreviousBase = Join-Path $runtime 'restore-previous-base'
$restoreNewBase = Join-Path $runtime 'restore-new-base'
$archivedRestoreSource = Join-Path $runtime 'archived-restore-source-base'
$faultBase = Join-Path $runtime 'fault-base'
$ankiExe = 'C:\Users\sanya\AppData\Local\Programs\Anki\Anki.exe'
$seedBase = Join-Path $repoRoot '.scratch\0003-companion-lifecycle-recovery-prototype\runtime\baseline-offline-copy'
$productionSource = Join-Path $repoRoot 'companion\ankigta_companion'
$harnessSource = Join-Path $PSScriptRoot 'anki_ticket_04_harness'
$profileA = 'ANKIGTA_P0003_A'
$profileB = 'ANKIGTA_P0003_B'

if (Test-Path -LiteralPath $runtime) {
    throw "Integration runtime already exists; refusing to overwrite: $runtime"
}
if (-not (Test-Path -LiteralPath $ankiExe)) {
    throw "Anki 26.05 executable not found: $ankiExe"
}
if (-not (Test-Path -LiteralPath $seedBase)) {
    throw "Disposable Anki seed base not found: $seedBase"
}
if ((Get-Item -LiteralPath $ankiExe).VersionInfo.ProductVersion -ne '26.5') {
    throw 'The installed Anki executable is not version 26.05'
}
if (Get-Process -Name 'anki' -ErrorAction SilentlyContinue) {
    throw 'Close Anki before running the ticket 04 integration matrix'
}

New-Item -ItemType Directory -Path $runtime, $evidence | Out-Null

function Copy-Seed([string]$target) {
    New-Item -ItemType Directory -Path $target | Out-Null
    Get-ChildItem -LiteralPath $seedBase -Force |
        Where-Object { $_.Name -ne 'addons21' } |
        Copy-Item -Destination $target -Recurse
}

function Install-Addons([string]$base) {
    $addons = Join-Path $base 'addons21'
    $productionTarget = Join-Path $addons 'ankigta_companion'
    $harnessTarget = Join-Path $addons 'ankigta_ticket_04_harness'
    New-Item -ItemType Directory -Path $addons -Force | Out-Null
    if (-not (Test-Path -LiteralPath $productionTarget)) {
        Copy-Item -LiteralPath $productionSource -Destination $productionTarget -Recurse
    }
    if (-not (Test-Path -LiteralPath $harnessTarget)) {
        Copy-Item -LiteralPath $harnessSource -Destination $harnessTarget -Recurse
    }
}

function Start-Ticket04Anki(
    [string]$base,
    [string]$phase,
    [string]$profile
) {
    Install-Addons $base
    $env:ANKIGTA_TICKET04_EVIDENCE = $evidence
    $env:ANKIGTA_TICKET04_PHASE = $phase
    $process = Start-Process `
        -FilePath $ankiExe `
        -ArgumentList @('-b', $base, '-l', 'en', '-p', $profile) `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Anki exited with code $($process.ExitCode) during $phase"
    }
    $failure = Join-Path $evidence "failure-$phase.json"
    if (Test-Path -LiteralPath $failure) {
        throw "Integration harness failed during $phase"
    }
}

Copy-Seed $primaryBase
Start-Ticket04Anki $primaryBase 'initialize-a' $profileA
Start-Ticket04Anki $primaryBase 'restart-a' $profileA

$sourceCollection = Join-Path $primaryBase "$profileA\collection.anki2"
$targetCollection = Join-Path $primaryBase "$profileB\collection.anki2"
Copy-Item -LiteralPath $sourceCollection -Destination $targetCollection -Force
Start-Ticket04Anki $primaryBase 'collision-b-rename' $profileB

Copy-Item -LiteralPath $primaryBase -Destination $presentCopyBase -Recurse
Start-Ticket04Anki $presentCopyBase 'present-copy' $profileA

Copy-Seed $restoreSourceBase
Start-Ticket04Anki $restoreSourceBase 'initialize-restore-source' $profileA
Copy-Item -LiteralPath $restoreSourceBase -Destination $restorePreviousBase -Recurse
Copy-Item -LiteralPath $restoreSourceBase -Destination $restoreNewBase -Recurse
$resolvedRuntime = (Resolve-Path -LiteralPath $runtime).Path
$resolvedRestoreSource = (Resolve-Path -LiteralPath $restoreSourceBase).Path
if (-not $resolvedRestoreSource.StartsWith($resolvedRuntime)) {
    throw "Restore source escaped integration runtime: $resolvedRestoreSource"
}
Move-Item -LiteralPath $restoreSourceBase -Destination $archivedRestoreSource
Start-Ticket04Anki $restorePreviousBase 'restore-previous' $profileA
Start-Ticket04Anki $restoreNewBase 'restore-new' $profileA

Copy-Seed $faultBase
Start-Ticket04Anki $faultBase 'fault-injection' $profileA

$env:PYTHONIOENCODING = 'utf-8'
python (Join-Path $PSScriptRoot 'verify_anki_ticket_04_evidence.py') $evidence
if ($LASTEXITCODE -ne 0) {
    throw 'Anki ticket 04 evidence verification failed'
}
