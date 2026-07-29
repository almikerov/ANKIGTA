param(
    [string]$MtaServerRoot = $env:ANKIGTA_MTA_SERVER_ROOT
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

if (-not $MtaServerRoot) {
    $prototypeRoot = Join-Path $repoRoot '.scratch\0004-mta-loopback-transport-prototype\runtime\mta-package\server'
    if (Test-Path -LiteralPath $prototypeRoot) {
        $MtaServerRoot = $prototypeRoot
    }
}

if (-not $MtaServerRoot) {
    throw 'Pass -MtaServerRoot or set ANKIGTA_MTA_SERVER_ROOT to MTA Server 1.6 build 24124.'
}

$env:ANKIGTA_MTA_SERVER_ROOT = (Resolve-Path -LiteralPath $MtaServerRoot).Path
python -m pytest tests/test_mta_ticket_05.py -q
if ($LASTEXITCODE -ne 0) {
    throw 'Ticket 05 real-MTA acceptance suite failed.'
}
