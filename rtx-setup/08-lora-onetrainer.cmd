@echo off
title RTX-Umbau - LoRA-Training (OneTrainer)
setlocal
set PIP_CACHE_DIR=D:\pip-cache
set HF_HOME=D:\hf-cache
echo ==========================================================
echo    WELLE 6 - Eigene LoRAs trainieren (OneTrainer)
echo ==========================================================
echo.
echo OneTrainer (Nerogar): GUI zum Trainieren eigener Bild-LoRAs.
echo Eigenes venv (NICHT die ComfyUI-venv mischen!), cu121-torch.
echo.
echo Erstes Projekt-Plan: RONNY-GESICHT-LoRA
echo   - 15-25 scharfe Fotos von dir (versch. Winkel/Licht, gleiches Gesicht)
echo   - SDXL-LoRA = easy auf 12GB (~20-40 min)
echo   - FLUX-LoRA = eng auf 12GB -^> ggf. Cloud-5090 (Minuten)
echo   - Ergebnis: .safetensors -^> in ComfyUI laden -^> "dich" frei generieren
echo.
echo Installation (clont nach D:\ai-lora\OneTrainer):
pause
if not exist "D:\ai-lora" mkdir "D:\ai-lora"
cd /d "D:\ai-lora"
if not exist "OneTrainer" (git clone --depth 1 https://github.com/Nerogar/OneTrainer.git) else (echo schon da)
cd OneTrainer
echo.
echo Setup (baut eigenes venv mit passendem torch):
echo   install.bat  ausfuehren (von OneTrainer mitgeliefert)
echo   danach start-ui.bat
echo (Am Tag pruefen wir, dass install.bat cu121-torch zieht, passend zur 3060.)
echo.
pause
