@echo off
title OVRLKD KI-Status (RAM / VRAM / GPU)
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
"C:\Users\User\AppData\Local\Programs\Ollama\ollama.exe" ps 2>nul
echo.

rem --- Dienste ---
echo [Dienste]
for %%P in (8080 8188 8000 8001 11434) do (
    netstat -ano 2>nul | find ":%%P " | find "LISTEN" >nul && echo   Port %%P: AKTIV || echo   Port %%P: aus
)
echo.
echo ============================================================
echo   Q = beenden   (sonst automatisch nach 5s aktualisieren)
echo ============================================================

timeout /t 5 /nobreak >nul
goto loop
