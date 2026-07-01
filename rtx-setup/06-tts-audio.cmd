@echo off
title RTX-Umbau - TTS / Voice-Cloning
setlocal
set COMFY_PY=D:\comfyui\venv\Scripts\python.exe
set NODES=D:\comfyui\ComfyUI\custom_nodes
set PIP_CACHE_DIR=D:\pip-cache
set HF_HOME=D:\hf-cache
echo ==========================================================
echo    WELLE 3 - TTS / Stimme (komplette Luecke schliessen)
echo ==========================================================
echo.
echo TTS-Audio-Suite (diodiogod) = 11 Engines in einem Node:
echo   Chatterbox (winzig, Voice-Clone, Emotionen) + VibeVoice (7B, Multi-Speaker)
echo   -^> deine eigene Stimme klonen aus einer .wav, mehrsprachig.
echo.
echo ACHTUNG numpy: TTS-Pakete wollen evtl. neueres numpy. Nach Install pruefen,
echo dass numpy 1.26.4 BLEIBT (sonst ReActor/LivePortrait kaputt). Notfalls:
echo   "%COMFY_PY%" -m pip install numpy==1.26.4
echo.
pause
cd /d "%NODES%"
if not exist "ComfyUI-TTS-Audio-Suite" (git clone --depth 1 https://github.com/diodiogod/TTS-Audio-Suite.git ComfyUI-TTS-Audio-Suite) else (echo schon da)
if exist "ComfyUI-TTS-Audio-Suite\requirements.txt" "%COMFY_PY%" -m pip install --no-input -r "ComfyUI-TTS-Audio-Suite\requirements.txt"
echo.
echo numpy-Check:
"%COMFY_PY%" -c "import numpy; print('numpy', numpy.__version__)"
echo.
echo Modelle laden Engines beim ersten Start (HF_HOME=D:\hf-cache).
echo Danach Kachel "Stimme" ins Studio bauen.
echo.
pause
