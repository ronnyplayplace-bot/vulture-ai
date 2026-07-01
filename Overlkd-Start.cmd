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

REM OLLAMA_MODELS is already set as an environment variable (from batenv.py) and
REM is inherited by "ollama serve".

REM 1) Ollama (model runtime), if not already active
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul || start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve

REM 2) Local Code-RAG (port %RAG_PORT%) - only if not already open
netstat -an | find ":%RAG_PORT% " | find "LISTENING" >nul
if errorlevel 1 (
    if exist "%~dp0rag\start-rag.cmd" ( start "Overlkd Memory" /min "%~dp0rag\start-rag.cmd" ) else ( echo [i] Code-RAG launcher not found - run the installer. )
)

REM 3) Open WebUI (port %WEBUI_PORT%) - optional local chat UI
netstat -an | find ":%WEBUI_PORT% " | find "LISTENING" >nul
if errorlevel 1 (
    if exist "%~dp0rag\start-webui.cmd" ( start "Overlkd WebUI" /min "%~dp0rag\start-webui.cmd" ) else ( echo [i] Open WebUI not installed - optional, skipping. )
)

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
