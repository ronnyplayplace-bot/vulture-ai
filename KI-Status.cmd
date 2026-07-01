@echo off
title OVRLKD KI-Status (RAM / VRAM / GPU)

REM Portable Pfade/Ports aus der Config laden (vulture\batenv.py) - einmalig vor der Schleife
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
for /f "usebackq delims=" %%L in (`"%PYEXE%" "%~dp0vulture\batenv.py" 2^>nul`) do %%L

:loop
cls
echo ============================================================
echo   OVRLKD KI-System Status   (aktualisiert alle 5s)
echo ============================================================
echo.

rem --- RAM ---
echo [RAM]
for /f "tokens=2" %%A in ('wmic OS get FreePhysicalMemory /value ^| find "="') do set FREERAM=%%A
for /f "tokens=2" %%A in ('wmic OS get TotalVisibleMemorySize /value ^| find "="') do set TOTALRAM=%%A
set /a USEDRAM=(%TOTALRAM%-%FREERAM%)/1024
set /a TOTALRAMMB=%TOTALRAM%/1024
echo   Belegt: %USEDRAM% MB / %TOTALRAMMB% MB
echo.

rem --- GPU & VRAM (nvidia-smi) ---
echo [GPU / VRAM]
nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>nul
if errorlevel 1 echo   (nvidia-smi nicht gefunden - Treiber pruefen)
echo.

rem --- Ollama Modelle ---
echo [Ollama - geladene Modelle]
"%OLLAMA_EXE%" ps 2>nul
echo.

rem --- Dienste ---
echo [Dienste]
for %%P in (%WEBUI_PORT% %COMFY_PORT% %TUNNEL_PORT% %RAG_PORT% %OLLAMA_PORT%) do (
    netstat -ano 2>nul | find ":%%P " | find "LISTEN" >nul && echo   Port %%P: AKTIV || echo   Port %%P: aus
)
echo.
echo ============================================================
echo   Q = beenden   (sonst automatisch nach 5s aktualisieren)
echo ============================================================

timeout /t 5 /nobreak >nul
goto loop
