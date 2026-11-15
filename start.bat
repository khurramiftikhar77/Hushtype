@echo off
REM First run: creates a virtual environment with Python 3.12 and installs dependencies.
REM Python 3.12 is used because some dependencies have no packages for newer versions yet.
cd /d "%~dp0"
if not exist .venv (
    py -V:3.12 --version >nul 2>&1 || goto :nopython
    echo Setting up Hushtype, this takes a few minutes the first time...
    py -V:3.12 -m venv .venv || goto :error
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\pip install -e . || goto :error
)
.venv\Scripts\python -m hushtype %*
goto :eof

:nopython
echo Python 3.12 is not installed. Install it by running:
echo     py install 3.12
echo then run start.bat again.
pause
goto :eof

:error
echo Setup failed. Delete the .venv folder and run start.bat again.
echo If it still fails, run "start.bat -v" in a terminal and share the output.
pause
