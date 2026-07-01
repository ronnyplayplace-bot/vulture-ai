@echo off
REM ==========================================================================
REM  Vulture AI -- local, private code-RAG server (127.0.0.1 only)
REM  Portable: resolves paths/ports/model from config.json via vulture\batenv.py.
REM  Your code never leaves this machine.
REM ==========================================================================
title Vulture AI - Code-RAG

REM Load portable paths/ports from the config (repo\vulture\batenv.py).
set "PYEXE=python"
where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
for /f "usebackq delims=" %%L in (`"%PYEXE%" "%~dp0..\vulture\batenv.py" 2^>nul`) do %%L

REM Fallbacks if batenv did not run (fresh clone, or a wrong default python like 3.14).
if not defined RAG_PORT set "RAG_PORT=8001"
REM RAG_PY MUST be the RAG venv's python (it has uvicorn/qdrant/fastembed) -- never a
REM random system python. Prefer batenv's value, then the known venv locations, only
REM then a bare python. (%~dp0.. is the install root; the venv lives under it.)
if defined RAG_PY if not exist "%RAG_PY%" set "RAG_PY="
if not defined RAG_PY if exist "%~dp0..\VultureAI\rag\venv\Scripts\python.exe" set "RAG_PY=%~dp0..\VultureAI\rag\venv\Scripts\python.exe"
if not defined RAG_PY if exist "%LOCALAPPDATA%\VultureAI\rag\venv\Scripts\python.exe" set "RAG_PY=%LOCALAPPDATA%\VultureAI\rag\venv\Scripts\python.exe"
if not defined RAG_PY set "RAG_PY=%PYEXE%"

REM QDRANT_PATH / RAG_DATA_DIR / FASTEMBED_CACHE_PATH / EMBED_MODEL /
REM RAG_COLLECTION are inherited from batenv above; the server falls back to
REM %LOCALAPPDATA%\VultureAI\rag\... for any that are still unset.
REM Fully local: no API key by default (auth stays optional).

echo Starting local Code-RAG on http://127.0.0.1:%RAG_PORT%  (Ctrl+C to stop)
cd /d "%~dp0api"
"%RAG_PY%" -m uvicorn main:app --host 127.0.0.1 --port %RAG_PORT%
