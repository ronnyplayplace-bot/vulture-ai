@echo off
title RTX-Umbau - Video-Nodes installieren
setlocal
set COMFY_PY=D:\comfyui\venv\Scripts\python.exe
set NODES=D:\comfyui\ComfyUI\custom_nodes
set PIP_CACHE_DIR=D:\pip-cache
echo ==========================================================
echo    WELLE 2 - ComfyUI Video-Nodes (LTX-2.3 + Wan 2.2)
echo ==========================================================
echo.
echo Clont Nodes nach %NODES% und installiert Deps in die ComfyUI-venv.
echo VideoHelperSuite ist schon installiert (uebersprungen).
echo.
pause
cd /d "%NODES%"

echo --- ComfyUI-GGUF (city96) - GGUF-Loader fuer Video-Modelle ---
if not exist "ComfyUI-GGUF" (git clone --depth 1 https://github.com/city96/ComfyUI-GGUF.git) else (echo schon da)

echo --- ComfyUI-LTXVideo (Lightricks) ---
if not exist "ComfyUI-LTXVideo" (git clone --depth 1 https://github.com/Lightricks/ComfyUI-LTXVideo.git) else (echo schon da)
if exist "ComfyUI-LTXVideo\requirements.txt" "%COMFY_PY%" -m pip install --no-input -r "ComfyUI-LTXVideo\requirements.txt"

echo --- ComfyUI-KJNodes (Kijai) - Helfer + Patches ---
if not exist "ComfyUI-KJNodes" (git clone --depth 1 https://github.com/kijai/ComfyUI-KJNodes.git) else (echo schon da)
if exist "ComfyUI-KJNodes\requirements.txt" "%COMFY_PY%" -m pip install --no-input -r "ComfyUI-KJNodes\requirements.txt"

echo --- ComfyUI-WanVideoWrapper (Kijai) - Wan 2.2 Block-Swap ---
if not exist "ComfyUI-WanVideoWrapper" (git clone --depth 1 https://github.com/kijai/ComfyUI-WanVideoWrapper.git) else (echo schon da)
if exist "ComfyUI-WanVideoWrapper\requirements.txt" "%COMFY_PY%" -m pip install --no-input -r "ComfyUI-WanVideoWrapper\requirements.txt"

echo.
echo FERTIG. ComfyUI neu starten, dann Modelle laden (siehe Playbook Welle 2).
echo WICHTIG: numpy danach pruefen - muss 1.26.4 bleiben (ReActor/LivePortrait):
"%COMFY_PY%" -c "import numpy; print('numpy', numpy.__version__)"
echo.
pause
