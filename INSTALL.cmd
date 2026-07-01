@echo off
setlocal enableextensions
title Vulture AI - Installer
cd /d "%~dp0"

echo ============================================================
echo    Vulture AI  -  by Overlkd Studio
echo    First-time setup. Downloads ComfyUI, models and the
echo    local AI models onto your PC. 100%% local, nothing leaves
echo    your machine. This can take a while - large downloads.
echo ============================================================
echo.

REM --- 1) Python 3.11 check ---
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
"%PYEXE%" --version >nul 2>nul
if errorlevel 1 goto no_python
echo [ok] Python found:
"%PYEXE%" --version

REM --- 2) Git check (recommended, not required to run) ---
where git >nul 2>nul || echo [note] Git not found - recommended for one-click updates. Get it at https://git-scm.com/download/win

echo.
echo Starting the installer...
echo.
"%PYEXE%" "%~dp0setup\install.py"
if errorlevel 1 goto install_failed

echo.
echo ============================================================
echo    Setup complete. Launching Vulture AI...
echo ============================================================
set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" "%~dp0studio.py"
exit /b 0

:no_python
echo.
echo [X] Python was not found.
echo     Install Python 3.11 64-bit, and TICK "Add python.exe to PATH".
echo     Opening the download page...
start "" https://www.python.org/downloads/
echo.
pause
exit /b 1

:install_failed
echo.
echo [X] The installer reported a problem. Scroll up to see what failed,
echo     then run INSTALL.cmd again - finished downloads are skipped.
echo.
pause
exit /b 1
