@echo off
REM First run: creates a virtual environment and installs dependencies.
cd /d "%~dp0"
if not exist .venv (
    echo Setting up LocalFlow, this takes a few minutes the first time...
    python -m venv .venv || goto :error
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\pip install -e . || goto :error
)
.venv\Scripts\python -m localflow %*
goto :eof

:error
echo Setup failed. Make sure Python 3.11 or newer is installed and on PATH.
pause
