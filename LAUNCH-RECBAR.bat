@echo off
title RECBAR — OBS Recording Companion
cd /d "%~dp0"

echo.
echo  RECBAR — OBS Recording Companion by KHET-1
echo  Ported to Windows for THUNDER_VOX
echo.

set PYTHONPATH=%CD%\recbar
.\venv\Scripts\python.exe -m recbar %*

echo.
echo  Press any key to close...
pause >nul
