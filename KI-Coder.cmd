@echo off
setlocal enabledelayedexpansion
title OVRLKD Coding-Agent (Aider)
set OLLAMA_API_BASE=http://127.0.0.1:11434

REM Auto-Tune: num_ctx automatisch an die aktuelle GPU anpassen (mehr VRAM = mehr Kontext)
"C:\Users\User\AppData\Local\Programs\Python\Python311\python.exe" "D:\OVRLKD-Studio\auto-tune-ctx.py"

cls
echo ==========================================================
echo    OVRLKD Coding-Agent  (Aider + lokale Modelle)
echo ==========================================================
echo.
echo   Modell auswaehlen:
echo   [1] qwen3.5:9b         (NEU, beste Wahl - ideal ab 1080 Ti)
echo   [2] qwen2.5-coder:7b   (Code-Spezialist, laeuft auf 6GB)
echo   [3] qwen3.5:4b         (NEU, schnell, 256K Kontext)
echo   [4] qwen3:14b          (groesste, langsam)
echo   [5] deepseek-r1:7b     (Debugging + Reasoning)
echo.
set /p "MODELL_WAHL=Modell [1-5, Enter=1]: "
if "!MODELL_WAHL!"=="" set "MODELL_WAHL=1"
if "!MODELL_WAHL!"=="1" set "MODELL=ollama_chat/qwen3.5:9b"
if "!MODELL_WAHL!"=="2" set "MODELL=ollama_chat/qwen2.5-coder:7b"
if "!MODELL_WAHL!"=="3" set "MODELL=ollama_chat/qwen3.5:4b"
if "!MODELL_WAHL!"=="4" set "MODELL=ollama_chat/qwen3:14b"
if "!MODELL_WAHL!"=="5" set "MODELL=ollama_chat/deepseek-r1:7b"
if "!MODELL!"=="" set "MODELL=ollama_chat/qwen2.5-coder:7b"

echo.
echo ==========================================================
echo.
echo   Arbeitsordner:
echo   Neues Projekt: Enter druecken, dann Name eingeben
echo   Bestehend: kompletten Pfad einfuegen
echo.
set "ORDNER="
set /p "ORDNER=Arbeitsordner (Pfad, oder Enter fuer neues Projekt): "

if "!ORDNER!"=="" (
    set /p "NAME=Name des neuen Projekts: "
    if "!NAME!"=="" set "NAME=neues-projekt"
    set "ORDNER=%USERPROFILE%\Desktop\!NAME!"
    if not exist "!ORDNER!" mkdir "!ORDNER!"
)

if not exist "!ORDNER!" (
    echo Ordner nicht gefunden: !ORDNER!
    pause
    exit /b
)

cd /d "!ORDNER!"

REM Auto-Test/Lint-Repair-Loop pro Projekt einrichten (groesster Qualitaetshebel fuer lokale Modelle)
"C:\Users\User\AppData\Local\Programs\Python\Python311\python.exe" "D:\OVRLKD-Studio\setup-project-coding.py" "!ORDNER!"

echo.
echo Ordner : !ORDNER!
echo Modell : !MODELL!
echo Befehle: /help  /add datei  /run cmd  /architect  /exit
echo ----------------------------------------------------------
echo.
"D:\ai-coder\venv\Scripts\python.exe" -m aider --model !MODELL!
echo.
echo ==========================================================
echo   Aider wurde beendet. Fenster bleibt offen.
echo ==========================================================
pause
