@echo off
title RTX-Umbau - Beschleunigung
setlocal
set COMFY_PY=D:\comfyui\venv\Scripts\python.exe
set PIP_CACHE_DIR=D:\pip-cache
echo ==========================================================
echo    WELLE 1 - Beschleunigung (zuerst! multipliziert alles)
echo ==========================================================
echo.
echo 1) ComfyUI-Start von --lowvram auf --fast umstellen (12GB vertraegt das)
echo    -^> in studio.py ensure_comfy(): --lowvram durch --fast ersetzen
echo    (mache ich am Tag mit dir zusammen, ist eine Zeile)
echo.
echo 2) triton-windows fuer torch.compile (~10-30%% ueberall, laeuft auf cu121)
echo.
pause
"%COMFY_PY%" -m pip install --no-input triton-windows

echo.
echo 3) SageAttention 2 (optional, nur ~10-15%% auf Ampere - NICHT die 2x aus Blogs;
echo    die gelten fuer Blackwell). Bei Wan-Black-Frame-Bug: KJNodes-Patch nutzen.
echo    Installieren? (Enter = ja, sonst Fenster schliessen)
pause
"%COMFY_PY%" -m pip install --no-input sageattention

echo.
echo FERTIG. numpy-Check (muss 1.26.4 bleiben):
"%COMFY_PY%" -c "import numpy; print('numpy', numpy.__version__)"
echo.
echo HINWEIS: fp8 bringt auf der 3060 NUR VRAM-Ersparnis, 0%% Speed (kein fp8-HW).
echo Groesster Video-Speed kommt von Lightning-4-Step-LoRA (siehe Welle 2).
echo.
pause
