@echo off
REM Start the OVRLKD Studio GUI (studio.py) next to this launcher.
REM Prefer the env-based Python 3.11 install; fall back to pythonw on PATH.
set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
start "" "%PYW%" "%~dp0studio.py"
exit
