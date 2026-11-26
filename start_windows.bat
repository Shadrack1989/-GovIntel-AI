@echo off
setlocal
cd /d "%~dp0"
title GovIntel AI AI
echo ==== GovIntel AI AI launcher ====
echo Folder: %CD%

if not exist run.py goto notfound

set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if "%PY%"=="" python --version >nul 2>&1 && set PY=python
if "%PY%"=="" goto nopython
echo Using: %PY%
%PY% --version

if exist .venv\Scripts\activate.bat goto haveenv
echo Creating environment (first run only)...
%PY% -m venv .venv
if errorlevel 1 goto fail
call .venv\Scripts\activate.bat
echo Installing packages - this can take a few minutes...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto fail
goto run

:haveenv
call .venv\Scripts\activate.bat

:run
echo Starting GovIntel AI. Open http://localhost:8000 if the browser does not open.
python run.py
goto end

:notfound
echo ERROR: run.py not found here. Extract the zip first (Right-click - Extract All), then open the inner GovIntelAI folder.
goto end

:nopython
echo ERROR: Python was not found. Install Python 3.11+ from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH". If already installed, turn off the Microsoft Store
echo python shortcut: Settings - Apps - Advanced app settings - App execution aliases.
goto end

:fail
echo.
echo ERROR: setup failed - see the messages above.

:end
echo.
pause
