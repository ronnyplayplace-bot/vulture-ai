@echo off
title OVRLKD Studio KI
echo ===================================================
echo    OVRLKD Studio KI wird gestartet ...
echo    (Ollama + Code-RAG + VPS-Tunnel + WebUI)
echo ===================================================

REM Portable Pfade/Ports aus der Config laden (vulture\batenv.py)
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
for /f "usebackq delims=" %%L in (`"%PYEXE%" "%~dp0vulture\batenv.py" 2^>nul`) do %%L

REM OLLAMA_MODELS ist bereits als Umgebungsvariable gesetzt (aus batenv.py) und
REM wird an "ollama serve" vererbt.

REM 1) Ollama (Modell-Runtime), falls nicht aktiv
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul || start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve

REM 2) Lokales Code-RAG (Port %RAG_PORT%) - nur wenn nicht schon offen
netstat -an | find ":%RAG_PORT% " | find "LISTENING" >nul || start "OVRLKD Memory" /min "%TOOLS_DIR%\start-local-memory.cmd"

REM 3) VPS-Tunnel fuer Chat-Gedaechtnis (Port %TUNNEL_PORT%)
netstat -an | find ":%TUNNEL_PORT% " | find "LISTENING" >nul || start "OVRLKD Tunnel" /min "%TOOLS_DIR%\start-tunnel.cmd"

REM 4) Open WebUI (Port %WEBUI_PORT%)
netstat -an | find ":%WEBUI_PORT% " | find "LISTENING" >nul || start "OVRLKD WebUI" /min "%TOOLS_DIR%\start-webui.cmd"

REM 5) ComfyUI (Port %COMFY_PORT%) - optional, nur wenn bereits installiert
if exist "%COMFY_PY%" (
    netstat -an | find ":%COMFY_PORT% " | find "LISTENING" >nul || start "OVRLKD Bilder" /min /D "%COMFY_DIR%" "%COMFY_PY%" main.py --listen 127.0.0.1 --port %COMFY_PORT% --output-directory "%OUTPUT_DIR%" --cuda-device 0 --lowvram
)

REM 6) Browser oeffnen (ausser beim Autostart mit Argument "silent")
if /I "%~1"=="silent" goto ende
echo.
echo Warte kurz, bis alles laeuft, dann oeffnet sich der Browser ...
timeout /t 14 /nobreak >nul
start "" http://localhost:%WEBUI_PORT%

:ende
exit
