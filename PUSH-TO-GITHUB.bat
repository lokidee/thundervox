@echo off
title PUSH THUNDER_VOX TO GITHUB
echo.
echo  ===================================
echo   PUSHING THUNDER_VOX TO GITHUB
echo   Account: lokidee
echo  ===================================
echo.

REM Install Git if needed
where git >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [!] Git not found — installing...
    winget install Git.Git --accept-package-agreements --accept-source-agreements
    echo.
    echo [!] CLOSE this window, REOPEN, run this again.
    pause
    exit /b 0
)

cd /d "%~dp0"

echo [1] Setting up git...
git config user.name "lokidee"
git config user.email "12268993+lokidee@users.noreply.github.com"

echo [2] Initializing repo...
if not exist ".git" (
    git init
    git remote add origin https://github.com/lokidee/thundervox.git
)

echo [3] Adding files...
git add main.py presets.json requirements.txt README.md LICENSE CONTRIBUTING.md .gitignore
git add LAUNCH-GOD.bat LAUNCH.bat LAUNCH-RECBAR.bat
if exist UnifrakturMaguntia-Regular.ttf git add UnifrakturMaguntia-Regular.ttf
if exist sounds git add sounds/

echo [4] Committing...
git commit -m "THUNDER_VOX — real-time Warhammer 40k voice modulator"

echo [5] Pushing to github.com/lokidee/thundervox ...
git branch -M main
git push -u origin main --force

echo.
echo  ===================================
echo   DONE! Check: github.com/lokidee/thundervox
echo  ===================================
echo.
echo  If a browser popped up, log in and run this again.
echo.
pause
