@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "LOCAL_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"

if exist "%LOCAL_PYTHON%" (
    "%LOCAL_PYTHON%" -c "import sys; raise SystemExit(sys.version_info ^< (3,11))" >nul 2>nul
    if not errorlevel 1 goto run_local
)

py -3.11 -c "import sys; raise SystemExit(sys.version_info ^< (3,11))" >nul 2>nul
if not errorlevel 1 goto run_py

python -c "import sys; raise SystemExit(sys.version_info ^< (3,11))" >nul 2>nul
if not errorlevel 1 goto run_python

echo Python 3.11 or newer was not found. Install Python, then create the local .venv.
pause
exit /b 1

:run_local
"%LOCAL_PYTHON%" "%SCRIPT_DIR%watch_mta.py" --config "%SCRIPT_DIR%config.json" %*
goto finished

:run_py
py -3.11 "%SCRIPT_DIR%watch_mta.py" --config "%SCRIPT_DIR%config.json" %*
goto finished

:run_python
python "%SCRIPT_DIR%watch_mta.py" --config "%SCRIPT_DIR%config.json" %*

:finished
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo Hot Reload exited with code %EXIT_CODE%. Review the message above.
    pause
)
exit /b %EXIT_CODE%
