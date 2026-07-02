@echo off
title Overlkd Studio AI
echo ===================================================
echo    Starting Overlkd Studio AI ...
echo    (Ollama + Code-RAG + WebUI)
echo ===================================================

REM Load portable paths/ports from the config (vulture\batenv.py)
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "VENVBAT=%TEMP%\vulture_env_%RANDOM%.bat"
"%PYEXE%" "%~dp0vulture\batenv.py" > "%VENVBAT%" 2>nul
if exist "%VENVBAT%" call "%VENVBAT%"
del "%VENVBAT%" 2>nul

REM Fallbacks if batenv did not run (fresh clone / wrong default python).
if not defined COMFY_VRAM_FLAG set "COMFY_VRAM_FLAG=--lowvram"
if not defined CUDA_DEVICE set "CUDA_DEVICE=0"

REM OLLAMA_MODELS is already set as an environment variable (from batenv.py) and
REM is inherited by "ollama serve".

REM 1) Ollama (model runtime), if not already active
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul || start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve

REM 2) Local Code-RAG (port %RAG_PORT%) - only if not already open
netstat -an | find ":%RAG_PORT% " | find "LISTENING" >nul
if errorlevel 1 (
    if exist "%~dp0rag\start-rag.cmd" ( start "Overlkd Memory" /min "%~dp0rag\start-rag.cmd" ) else ( echo [i] Code-RAG launcher not found - run the installer. )
)

REM 3) Open WebUI (port %WEBUI_PORT%) - optional local chat UI.
REM Prefer the hidden .vbs launcher (no console window at all), like the studio's
REM Chat card does; the minimized .cmd is only the fallback.
netstat -an | find ":%WEBUI_PORT% " | find "LISTENING" >nul
if errorlevel 1 (
    if exist "%~dp0rag\start-webui.vbs" ( start "" wscript "%~dp0rag\start-webui.vbs" ) else if exist "%~dp0rag\start-webui.cmd" ( start "Overlkd WebUI" /min "%~dp0rag\start-webui.cmd" ) else ( echo [i] Open WebUI not installed - optional, skipping. )
)

REM 4) ComfyUI (port %COMFY_PORT%) - optional, only if already installed.
REM VRAM flag + CUDA device come from config/auto-detect (batenv) so an RTX card
REM is not crippled by a hardcoded --lowvram.
if exist "%COMFY_PY%" (
    netstat -an | find ":%COMFY_PORT% " | find "LISTENING" >nul || start "Overlkd Images" /min /D "%COMFY_DIR%" "%COMFY_PY%" main.py --listen 127.0.0.1 --port %COMFY_PORT% --output-directory "%OUTPUT_DIR%" --cuda-device %CUDA_DEVICE% %COMFY_VRAM_FLAG%
)

REM 5) Open the browser (except on autostart with the "silent" argument)
if /I "%~1"=="silent" goto ende
echo.
echo Waiting a moment for everything to come up, then the browser opens ...
timeout /t 14 /nobreak >nul
start "" http://localhost:%WEBUI_PORT%

:ende
exit
