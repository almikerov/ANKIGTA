$ErrorActionPreference = "Stop"
$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalPython = Join-Path $ScriptDirectory ".venv\Scripts\python.exe"
$Watcher = Join-Path $ScriptDirectory "watch_mta.py"
$Config = Join-Path $ScriptDirectory "config.json"

if (Test-Path -LiteralPath $LocalPython -PathType Leaf) {
    $PythonCommand = $LocalPython
    $PythonPrefix = @()
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCommand = "python"
    $PythonPrefix = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonCommand = "py"
    $PythonPrefix = @("-3")
} else {
    Write-Host "Python 3.11 or newer was not found. Install Python, then create the local .venv." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

$ErrorActionPreference = "Continue"
& $PythonCommand @PythonPrefix $Watcher --config $Config @args
$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    Write-Host "Hot Reload exited with code $ExitCode. Review the message above." -ForegroundColor Red
    Read-Host "Press Enter to close"
}
exit $ExitCode
