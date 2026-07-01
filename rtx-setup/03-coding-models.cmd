@echo off
title RTX-Umbau - Coding-Modelle
echo ==========================================================
echo    WELLE 7 - Bessere Coding-Modelle (12GB nutzen)
echo ==========================================================
echo.
echo Laedt staerkere Coder nach Ollama (OLLAMA_MODELS=D:\ollama\models).
echo Auf der RTX 3060 passt jetzt 14B komplett auf die GPU.
echo.
echo Hinweis: Fuer bestes Tool-Calling sind Unsloth-GGUFs besser als die
echo Standard-Ollama-Quants. Schnellster Weg = Ollama-Library (unten).
echo Fuer Unsloth: GGUF von huggingface.co/unsloth laden + via Modelfile importieren.
echo.
pause

echo --- Qwen2.5-Coder-14B (neuer Default, ~9GB, passt auf 12GB) ---
ollama pull qwen2.5-coder:14b

echo.
echo --- OPTIONAL: Qwen3-Coder-30B (MoE, 3B aktiv, Offload->RAM, harte Tasks) ---
echo (Gross! Nur wenn 32GB RAM da sind. Enter zum Laden, sonst Fenster schliessen)
pause
ollama pull qwen3-coder:30b

echo.
echo FERTIG. Danach in KI-Coder.cmd Menue qwen2.5-coder:14b als [1] setzen
echo und in auto-tune-ctx.py ist 14B bereits beruecksichtigt (num_ctx auto).
echo.
echo Test: KI-Coder starten, Projekt mit Tests oeffnen -> Auto-Test-Loop laeuft.
echo.
pause
