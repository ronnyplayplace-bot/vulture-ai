@echo off
title RTX-Umbau - Musik (ACE-Step)
setlocal
set COMFY_PY=D:\comfyui\venv\Scripts\python.exe
set NODES=D:\comfyui\ComfyUI\custom_nodes
set PIP_CACHE_DIR=D:\pip-cache
set HF_HOME=D:\hf-cache
echo ==========================================================
echo    WELLE 4 - Musik fuer Gameplays (ACE-Step 1.5)
echo ==========================================================
echo.
echo Text -^> Musik/Instrumental, ^<4GB VRAM, royaltyfrei lokal.
echo z.B. "dark synthwave, driving beat" oder "chill lofi background".
echo ComfyUI hat ACE-Step teils NATIV - erst pruefen ob Nodes schon da sind,
echo bevor ein Extra-Node geclont wird (Playbook: neueste Variante checken).
echo.
echo Variante A (nativ, bevorzugt): ComfyUI updaten, ACE-Step-Template nutzen,
echo   Modell ace_step_v1 nach D:\comfyui\ComfyUI\models\checkpoints\ laden.
echo Variante B (Node): github.com/ace-step ... ComfyUI-Wrapper clonen.
echo.
echo Am Tag entscheiden wir A vs B nach aktuellem Stand.
echo.
pause
echo (Platzhalter - konkrete Schritte am RTX-Tag, je nach neuestem ACE-Step-Stand)
pause
