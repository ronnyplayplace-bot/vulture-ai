@echo off
setlocal enabledelayedexpansion
title Overlkd Coding Agent (Aider)

REM Load portable paths/ports from the config (vulture\batenv.py)
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
set "VENVBAT=%TEMP%\vulture_env_%RANDOM%.bat"
"%PYEXE%" "%~dp0vulture\batenv.py" > "%VENVBAT%" 2>nul
if exist "%VENVBAT%" call "%VENVBAT%"
del "%VENVBAT%" 2>nul

REM AIDER_PY must be Aider's venv python (setup/install.py) -- never a random system
REM python (e.g. a 3.14 on PATH without aider). Prefer batenv's value, then the known
REM venv locations (%~dp0 is the install root; the venv lives under it).
if defined AIDER_PY if not exist "%AIDER_PY%" set "AIDER_PY="
if not defined AIDER_PY if exist "%~dp0VultureAI\aider\venv\Scripts\python.exe" set "AIDER_PY=%~dp0VultureAI\aider\venv\Scripts\python.exe"
if not defined AIDER_PY if exist "%LOCALAPPDATA%\VultureAI\aider\venv\Scripts\python.exe" set "AIDER_PY=%LOCALAPPDATA%\VultureAI\aider\venv\Scripts\python.exe"

set OLLAMA_API_BASE=http://127.0.0.1:%OLLAMA_PORT%

REM Auto-tune: adjust num_ctx automatically to the current GPU (more VRAM = more context)
"%SYSTEM_PY%" "%~dp0auto-tune-ctx.py"

cls
echo ==========================================================
echo    Overlkd Coding Agent  (Aider + local models)
echo ==========================================================
echo.
echo   Choose a model:
echo   [1] qwen3.5:9b         (NEW, best choice - ideal from a 1080 Ti up)
echo   [2] qwen2.5-coder:7b   (code specialist, runs on 6GB)
echo   [3] qwen3.5:4b         (NEW, fast, 256K context)
echo   [4] qwen3:14b          (largest, slow)
echo   [5] deepseek-r1:7b     (debugging + reasoning)
echo.
REM Default = the preferred qwen3.5:9b IF it's actually installed, otherwise the
REM always-present qwen2.5-coder:7b -- so a fresh clone works on Enter either way.
set "DEF=2"
ollama list 2>nul | findstr /I "qwen3.5:9b" >nul && set "DEF=1"
set /p "MODELL_WAHL=Model [1-5, Enter=!DEF!]: "
if "!MODELL_WAHL!"=="" set "MODELL_WAHL=!DEF!"
if "!MODELL_WAHL!"=="1" set "MODELL=ollama_chat/qwen3.5:9b"
if "!MODELL_WAHL!"=="2" set "MODELL=ollama_chat/qwen2.5-coder:7b"
if "!MODELL_WAHL!"=="3" set "MODELL=ollama_chat/qwen3.5:4b"
if "!MODELL_WAHL!"=="4" set "MODELL=ollama_chat/qwen3:14b"
if "!MODELL_WAHL!"=="5" set "MODELL=ollama_chat/deepseek-r1:7b"
if "!MODELL!"=="" set "MODELL=ollama_chat/qwen2.5-coder:7b"

echo.
echo ==========================================================
echo.
echo   Working folder:
echo   New project: press Enter, then type a name
echo   Existing: paste the full path
echo.
set "ORDNER="
set /p "ORDNER=Working folder (path, or Enter for a new project): "

if "!ORDNER!"=="" (
    set /p "NAME=Name of the new project: "
    if "!NAME!"=="" set "NAME=new-project"
    set "ORDNER=%USERPROFILE%\Desktop\!NAME!"
    if not exist "!ORDNER!" mkdir "!ORDNER!"
)

if not exist "!ORDNER!" (
    echo Folder not found: !ORDNER!
    pause
    exit /b
)

cd /d "!ORDNER!"

REM Set up the auto-test/lint repair loop per project (biggest quality lever for local models)
"%SYSTEM_PY%" "%~dp0setup-project-coding.py" "!ORDNER!"

echo.
echo Folder : !ORDNER!
echo Model  : !MODELL!
echo Commands: /help  /add file  /run cmd  /architect  /exit
echo ----------------------------------------------------------
echo.
if "!AIDER_PY!"=="" (
    echo   [!] Aider is not installed yet.
    echo       Run once:  python setup\install.py --steps aider
    echo       ^(or use the Setup window's "Install everything"^).
    echo.
    pause
    exit /b 1
)
"%AIDER_PY%" -m aider --model !MODELL!
echo.
echo ==========================================================
echo   Aider has exited. This window stays open.
echo ==========================================================
pause
