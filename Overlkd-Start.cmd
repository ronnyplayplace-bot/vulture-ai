@echo off
title Overlkd Studio AI
echo ===================================================
echo    Starting Overlkd Studio AI ...
echo    (Ollama + Code-RAG + WebUI)
echo ===================================================

REM Load portable paths/ports from the config (vulture\batenv.py)
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
for /f "usebackq delims=" %%L in (`"%PYEXE%" "%~dp0vulture\batenv.py" 2^>nul`) do %%L

REM OLLAMA_MODELS is already set as an environment variable (from batenv.py) and
REM is inherited by "ollama serve".

REM 1) Ollama (model runtime), if not already active
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul || start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve

REM 2) Local Code-RAG (port %RAG_PORT%) - only if not already open
netstat -an | find ":%RAG_PORT% " | find "LISTENING" >nul || start "Overlkd Memory" /min "%TOOLS_DIR%\start-local-memory.cmd"

REM 3) Open WebUI (port %WEBUI_PORT%)
netstat -an | find ":%WEBUI_PORT% " | find "LISTENING" >nul || start "Overlkd WebUI" /min "%TOOLS_DIR%\start-webui.cmd"

REM 4) ComfyUI (port %COMFY_PORT%) - optional, only if already installed
if exist "%COMFY_PY%" (
    netstat -an | find ":%COMFY_PORT% " | find "LISTENING" >nul || start "Overlkd Images" /min /D "%COMFY_DIR%" "%COMFY_PY%" main.py --listen 127.0.0.1 --port %COMFY_PORT% --output-directory "%OUTPUT_DIR%" --cuda-device 0 --lowvram
)

REM 5) Open the browser (except on autostart with the "silent" argument)
if /I "%~1"=="silent" goto ende
echo.
echo Waiting a moment for everything to come up, then the browser opens ...
timeout /t 14 /nobreak >nul
start "" http://localhost:%WEBUI_PORT%

:ende
exit
