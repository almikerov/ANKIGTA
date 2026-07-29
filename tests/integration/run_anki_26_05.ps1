$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$runtime = Join-Path $repoRoot '.scratch\ticket-01-anki-integration-runtime'
$evidence = Join-Path $runtime 'evidence'
$setupBase = Join-Path $runtime 'setup-base'
$testBase = Join-Path $runtime 'test-base'
$ankiExe = 'C:\Users\sanya\AppData\Local\Programs\Anki\Anki.exe'
$seedBase = Join-Path $repoRoot '.scratch\0002-filtered-deck-fsrs-admission-prototype\runtime\baseline-offline-copy'
$harnessSource = Join-Path $PSScriptRoot 'anki_harness'
$productionSource = Join-Path $repoRoot 'companion\ankigta_companion'

if (Test-Path -LiteralPath $runtime) {
    throw "Integration runtime already exists; refusing to overwrite: $runtime"
}
if (-not (Test-Path -LiteralPath $ankiExe)) {
    throw "Anki 26.05 executable not found: $ankiExe"
}
if (-not (Test-Path -LiteralPath $seedBase)) {
    throw "Disposable Anki 26.05 seed profile not found: $seedBase"
}
if ((Get-Item -LiteralPath $ankiExe).VersionInfo.ProductVersion -ne '26.5') {
    throw 'The installed Anki executable is not version 26.05'
}
if (Get-Process -Name 'anki' -ErrorAction SilentlyContinue) {
    throw 'Close Anki before running the ticket 01 integration test'
}

New-Item -ItemType Directory -Path $setupBase, $evidence | Out-Null
Get-ChildItem -LiteralPath $seedBase -Force |
    Where-Object { $_.Name -ne 'addons21' } |
    Copy-Item -Destination $setupBase -Recurse

function Install-Harness([string]$base) {
    $target = Join-Path $base 'addons21\ankigta_ticket_01_harness'
    New-Item -ItemType Directory -Path $target -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $harnessSource '__init__.py') -Destination $target
}

function Install-ProductionAddon([string]$base) {
    $addons = Join-Path $base 'addons21'
    New-Item -ItemType Directory -Path $addons -Force | Out-Null
    Copy-Item -LiteralPath $productionSource -Destination $addons -Recurse
}

function Start-IntegrationAnki([string]$base, [string]$phase) {
    $env:ANKIGTA_TICKET01_EVIDENCE = $evidence
    $env:ANKIGTA_TICKET01_PHASE = $phase
    $process = Start-Process `
        -FilePath $ankiExe `
        -ArgumentList @('-b', $base, '-l', 'en') `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Anki exited with code $($process.ExitCode) during $phase"
    }
}

Install-Harness $setupBase
Start-IntegrationAnki $setupBase 'setup'
if (-not (Test-Path -LiteralPath (Join-Path $evidence 'setup.json'))) {
    throw 'Disposable FSRS setup did not produce evidence'
}

Copy-Item -LiteralPath $setupBase -Destination $testBase -Recurse
Install-ProductionAddon $testBase
Start-IntegrationAnki $testBase 'verify'

$failures = Get-ChildItem -LiteralPath $evidence -Filter 'failure-*.json'
if ($failures) {
    throw "Integration harness failure: $($failures.Name -join ', ')"
}

$env:PYTHONIOENCODING = 'utf-8'
python (Join-Path $PSScriptRoot 'verify_anki_evidence.py') $evidence
if ($LASTEXITCODE -ne 0) {
    throw 'Anki integration evidence verification failed'
}
