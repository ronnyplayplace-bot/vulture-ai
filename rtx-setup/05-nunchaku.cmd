@echo off
title RTX-Umbau - Nunchaku (INT4-Turbo fuer Bilder)
setlocal
set COMFY_PY=D:\comfyui\venv\Scripts\python.exe
set NODES=D:\comfyui\ComfyUI\custom_nodes
set PIP_CACHE_DIR=D:\pip-cache
echo ==========================================================
echo    WELLE 5 - Nunchaku (INT4 fuer FLUX / Qwen-Image)
echo ==========================================================
echo.
echo ~3x schneller, ~3.5x weniger VRAM fuer FLUX/Qwen-Image.
echo Laeuft auf 3060 (sm_86, cap^>=7.5 noetig - 3060 ok).
echo NICHT fuer Video (nur Bild-Diffusion).
echo.
echo !! WICHTIG !! Das Nunchaku-WHEEL muss exakt zu deiner Umgebung passen:
echo    torch 2.5.1 + cu121 + Python-Version der ComfyUI-venv.
echo    -^> Richtiges Wheel von github.com/nunchaku-ai/nunchaku/releases holen.
echo    Pruefe vorher die Python-Version:
"%COMFY_PY%" --version
echo.
echo 1) ComfyUI-Node:
pause
cd /d "%NODES%"
if not exist "ComfyUI-nunchaku" (git clone --depth 1 https://github.com/nunchaku-ai/ComfyUI-nunchaku.git) else (echo schon da)
echo.
echo 2) Nunchaku-Wheel installieren (Pfad/URL des passenden Wheels hier eintragen):
echo    "%COMFY_PY%" -m pip install ^<nunchaku-wheel-url-fuer-torch2.5-cu121-pyXX^>
echo    (am Tag pruefen wir die neueste Release gemeinsam)
echo.
echo Danach Qwen-Image-Edit / FLUX als svdq-int4 laden (siehe Playbook Welle 5).
echo.
pause
