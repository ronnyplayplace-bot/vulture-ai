@echo off
title OVRLKD Studio KI
echo ===================================================
echo    OVRLKD Studio KI wird gestartet ...
echo    (Ollama + Code-RAG + VPS-Tunnel + WebUI)
echo ===================================================

set OLLAMA_MODELS=D:\ollama\models

REM 1) Ollama (Modell-Runtime), falls nicht aktiv
tasklist /FI "IMAGENAME eq ollama.exe" | find /I "ollama.exe" >nul || start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve

REM 2) Lokales Code-RAG (Port 8001) - nur wenn nicht schon offen
netstat -an | find ":8001 " | find "LISTENING" >nul || start "OVRLKD Memory" /min "C:\Users\User\ai-memory-tools\start-local-memory.cmd"

REM 3) VPS-Tunnel fuer Chat-Gedaechtnis (Port 8000)
netstat -an | find ":8000 " | find "LISTENING" >nul || start "OVRLKD Tunnel" /min "C:\Users\User\ai-memory-tools\start-tunnel.cmd"

REM 4) Open WebUI (Port 8080)
netstat -an | find ":8080 " | find "LISTENING" >nul || start "OVRLKD WebUI" /min "C:\Users\User\ai-memory-tools\start-webui.cmd"

REM 5) ComfyUI (Port 8188) - optional, nur wenn bereits installiert
if exist "D:\comfyui\venv\Scripts\python.exe" (
    netstat -an | find ":8188 " | find "LISTENING" >nul || start "OVRLKD Bilder" /min /D "D:\comfyui\ComfyUI" "D:\comfyui\venv\Scripts\python.exe" main.py --listen 127.0.0.1 --port 8188 --output-directory "D:\comfyui\output" --cuda-device 0 --lowvram
)

REM 6) Browser oeffnen (ausser beim Autostart mit Argument "silent")
if /I "%~1"=="silent" goto ende
echo.
echo Warte kurz, bis alles laeuft, dann oeffnet sich der Browser ...
timeout /t 14 /nobreak >nul
start "" http://localhost:8080

:ende
exit
