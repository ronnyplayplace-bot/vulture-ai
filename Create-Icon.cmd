@echo off
REM Create the "Vulture AI" launcher (with the vulture logo) on your Desktop
REM and in this folder. Double-click, done. Safe to run again anytime.
title Vulture AI - create launcher
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
"%PYEXE%" "%~dp0setup\install.py" --shortcut
echo.
echo Look for "Vulture AI" (with the logo) on your Desktop and in this folder.
pause
