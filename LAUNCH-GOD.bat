@echo off
setlocal enabledelayedexpansion
title THUNDER_VOX -- GOD-EMPEROR LAUNCHER
mode con: cols=90 lines=40
color 0E

echo.
echo  ===========================================================
echo  ########  ##  ## ##  ## ##  ## ####  ###### ####
echo    ##  ##  ##  ## ##  ## ### ## ## ##  ##     ## ##
echo    ##  ######  ## ##  ## ###### ## ## ###### #####
echo    ##  ##  ## ## ## ## ## ## ## ## ## ##     ## ##
echo    ##  ##  ##  ###   ###  ##  ## ####  ###### ## ##
echo  ===========================================================
echo     THUNDER_VOX -- Voice of the God-Emperor
echo     FOR THE EMPEROR! THE EMPEROR PROTECTS!
echo  ===========================================================
echo.

REM ============================================================
REM STEP 0: Navigate to script directory
REM ============================================================
cd /d "%~dp0"
echo [PATH] Working directory: %CD%
echo.

REM ============================================================
REM STEP 1: Find Python -- check everywhere
REM ============================================================
echo [PYTHON] Searching for Python...

set "PYTHON_CMD="

REM Check if python is in PATH
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

REM Check if python3 is in PATH
where python3 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

REM Check if py launcher exists (Windows Python Launcher)
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)

REM Check common install locations
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
    "C:\Python310\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python310\python.exe"
) do (
    if exist %%P (
        set "PYTHON_CMD=%%~P"
        goto :python_found
    )
)

REM Check Microsoft Store Python
for %%P in (
    "%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe"
    "%LOCALAPPDATA%\Microsoft\WindowsApps\python3.exe"
) do (
    if exist %%P (
        set "PYTHON_CMD=%%~P"
        goto :python_found
    )
)

REM PYTHON NOT FOUND -- big error
color 4E
echo.
echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo  !!!  PYTHON NOT FOUND -- THE MACHINE SPIRIT IS LOST  !!!
echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
echo.
echo  The Emperor commands you to install Python:
echo.
echo   1. Go to: https://www.python.org/downloads/
echo   2. Download Python 3.10 or newer
echo   3. IMPORTANT: Check "Add Python to PATH" during install
echo   4. Restart your computer
echo   5. Double-click LAUNCH-GOD.bat again
echo.
echo  THE EMPEROR PROTECTS. Install Python and return.
echo.
echo  Press any key to open python.org in your browser...
pause >nul
start https://www.python.org/downloads/
echo.
echo  This window stays open. Install Python, then run this again.
pause
exit /b 1

:python_found
echo [PYTHON] Found: %PYTHON_CMD%

REM Verify it actually works
%PYTHON_CMD% --version >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    color 4E
    echo [ERROR] Python found but won't run: %PYTHON_CMD%
    echo         Try reinstalling Python with "Add to PATH" checked.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('%PYTHON_CMD% --version 2^>^&1') do echo [PYTHON] Version: %%V
echo.

REM ============================================================
REM STEP 2: Create venv if it doesn't exist
REM ============================================================
if not exist "venv\Scripts\python.exe" (
    if not exist ".venv\Scripts\python.exe" (
        echo [VENV] No virtual environment found -- creating one...
        %PYTHON_CMD% -m venv venv
        if %ERRORLEVEL% NEQ 0 (
            color 4E
            echo [ERROR] Failed to create venv. Continuing with system Python...
            echo.
            set "PIP_CMD=%PYTHON_CMD% -m pip"
            set "RUN_CMD=%PYTHON_CMD%"
            goto :install_deps
        )
        echo [VENV] Created successfully!
    )
)

REM Activate venv
if exist "venv\Scripts\activate.bat" (
    echo [VENV] Activating venv...
    call venv\Scripts\activate.bat
    set "PIP_CMD=pip"
    set "RUN_CMD=python"
) else if exist ".venv\Scripts\activate.bat" (
    echo [VENV] Activating .venv...
    call .venv\Scripts\activate.bat
    set "PIP_CMD=pip"
    set "RUN_CMD=python"
) else (
    set "PIP_CMD=%PYTHON_CMD% -m pip"
    set "RUN_CMD=%PYTHON_CMD%"
)
echo.

REM ============================================================
REM STEP 3: Install dependencies
REM ============================================================
:install_deps
echo [DEPS] Installing dependencies (this may take a minute first time)...
echo.

REM Upgrade pip first (silently)
%PIP_CMD% install --upgrade pip --quiet 2>nul

REM Install requirements with progress
%PIP_CMD% install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    color 4E
    echo.
    echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo  !!!  DEPENDENCY INSTALL FAILED                    !!!
    echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo.
    echo  Try running this manually:
    echo    %PIP_CMD% install -r requirements.txt
    echo.
    echo  Common fixes:
    echo    - Run as Administrator
    echo    - Check internet connection
    echo    - Update pip: %PIP_CMD% install --upgrade pip
    echo.
    echo  THE EMPEROR PROTECTS. Fix the issue and try again.
    pause
    exit /b 1
)

echo.
echo [DEPS] All dependencies installed!
echo.

REM ============================================================
REM STEP 4: Launch THUNDER_VOX
REM ============================================================
color 0E
echo  ===========================================================
echo     FOR THE EMPEROR! LAUNCHING THUNDER_VOX...
echo     Speak and become the God-Emperor.
echo  ===========================================================
echo.

REM Run main.py and capture any crash
%RUN_CMD% main.py 2>&1
set EXIT_CODE=%ERRORLEVEL%

echo.
if %EXIT_CODE% NEQ 0 (
    color 4E
    echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo  !!!  THUNDER_VOX CRASHED -- Exit code: %EXIT_CODE%
    echo  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
    echo.
    echo  THE EMPEROR PROTECTS -- auto-healing suggestions:
    echo.
    echo   1. Check the error messages above
    echo   2. Try: %PIP_CMD% install -r requirements.txt --force-reinstall
    echo   3. Make sure your microphone is plugged in
    echo   4. Install BlackHole: github.com/deej-doo/BlackHole-Windows/releases
    echo   5. Restart your computer and try again
    echo.
    echo  Error logged to: %CD%\crash_log.txt
    echo  Session: %DATE% %TIME% >> crash_log.txt
    echo  Exit code: %EXIT_CODE% >> crash_log.txt
    echo.
) else (
    color 0A
    echo  ===========================================================
    echo     The Emperor rests. Session complete.
    echo     Fractal Faith Evolution Log: fractal_faith_log.txt
    echo  ===========================================================
)

echo.
echo  This window stays open. Press any key to close.
pause >nul
