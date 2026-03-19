@echo off
title THUNDER_VOX -- Voice of the God-King
color 0E
echo.
echo ============================================================
echo   THUNDER_VOX -- Launching God-Voice from WSL...
echo   The Emperor Protects.
echo ============================================================
echo.

REM Check if Python is installed on Windows first (preferred for audio)
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [DETECTED] Windows Python found -- using native audio access
    echo.

    REM Navigate to the project directory
    cd /d "%~dp0"

    REM Check for venv
    if exist "venv\Scripts\activate.bat" (
        echo [VENV] Activating virtual environment...
        call venv\Scripts\activate.bat
    ) else if exist ".venv\Scripts\activate.bat" (
        echo [VENV] Activating .venv...
        call .venv\Scripts\activate.bat
    ) else (
        echo [VENV] No venv found -- using system Python
        echo        To create one: python -m venv venv
    )

    echo.
    echo [INSTALL] Checking dependencies...
    pip install -r requirements.txt --quiet 2>nul

    echo.
    echo ============================================================
    echo   FOR THE EMPEROR! Starting THUNDER_VOX...
    echo ============================================================
    echo.

    python main.py

    echo.
    echo ============================================================
    echo   The Emperor rests. Session complete.
    echo ============================================================
    pause
    exit /b
)

REM Fallback: use WSL Python (may have limited audio)
echo [WARNING] No Windows Python found -- falling back to WSL Python
echo           Audio devices may not be available in WSL!
echo           Install Python on Windows for full audio access.
echo.

REM Get the WSL path for this batch file's directory
set "WIN_PATH=%~dp0"
echo [PATH] Windows: %WIN_PATH%

REM Convert Windows path to WSL path
for /f "tokens=*" %%i in ('wsl wslpath -u "%WIN_PATH%"') do set "WSL_PATH=%%i"
echo [PATH] WSL:     %WSL_PATH%
echo.

echo ============================================================
echo   FOR THE EMPEROR! Starting THUNDER_VOX via WSL...
echo ============================================================
echo.

wsl bash -c "cd '%WSL_PATH%' && pip install -r requirements.txt --quiet 2>/dev/null; python3 main.py"

echo.
echo ============================================================
echo   The Emperor rests. Session complete.
echo ============================================================
pause
