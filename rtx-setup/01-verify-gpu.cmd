@echo off
title RTX-Umbau - GPU verifizieren
echo ==========================================================
echo    WELLE 0 - GPU verifizieren (nach RTX-3060-Einbau)
echo ==========================================================
echo.
echo Erwartet: NVIDIA RTX 3060, 12GB, compute cap 8.6
echo.
nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv,noheader
echo.
for /f "tokens=3 delims=, " %%c in ('nvidia-smi --query-gpu=compute_cap --format=csv,noheader') do set CAP=%%c
echo Compute Capability: %CAP%
echo.
echo Pruefung:
echo   - cap 8.6  = RTX 3060 (Ampere)  -^> Tensor-Cores aktiv, cu121 perfekt
echo   - cap 6.1  = noch die alte GTX 1060 (Pascal) -^> Karte noch nicht getauscht!
echo.
echo Wenn 8.6: weiter mit 04-acceleration.cmd
echo Wenn Fehler/leer: Treiber pruefen (DDU + NVIDIA Studio-Treiber neu)
echo.
echo HINWEIS: Auslagerungsdatei jetzt auf D: vergroessern (64-128GB)!
echo   System -^> Erweiterte Einstellungen -^> Leistung -^> Virtueller Arbeitsspeicher
echo.
pause
