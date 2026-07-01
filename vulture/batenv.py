# -*- coding: utf-8 -*-
"""Emit ``set "VAR=value"`` lines so the ``.cmd`` launchers get portable paths.

Batch files cannot read ``config.json`` nor scan the drives for a ComfyUI /
Ollama / Python install, so every Overlkd ``.cmd`` sources this tiny helper at
the top::

    set "PYEXE=python"
    where python >nul 2>nul || set "PYEXE=%LOCALAPPDATA%\\Programs\\Python\\Python311\\python.exe"
    for /f "usebackq delims=" %%L in (`"%PYEXE%" "%~dp0vulture\\batenv.py" 2^>nul`) do %%L

After that loop the launcher can use ``%COMFY_PY%``, ``%OUTPUT_DIR%``,
``%OLLAMA_MODELS%``, ``%COMFY_PORT%`` etc. -- all resolved by
:mod:`vulture.config` (built-in defaults <- auto-detect <- ``config.json``), so a
fresh clone works on any machine.

Only ``set "..."`` lines are written to *stdout*; any diagnostics go to
*stderr* (which the launchers redirect to ``nul``) so they never pollute the
batch ``for /f`` capture.  The helper never raises out to the launcher: on any
failure it prints nothing and exits non-zero, leaving the variables unset so the
``.cmd`` can fall back / fail loudly on its own.
"""
from __future__ import annotations

import os
import sys

# Make the ``vulture`` package importable no matter the current directory
# (the launchers call us as "%~dp0vulture\batenv.py" from wherever they run).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from vulture.config import get_config


def _emit(name: str, value: object) -> str:
    """Return one batch ``set "NAME=VALUE"`` line (quoted -> spaces are safe)."""
    return f'set "{name}={value}"'


def main() -> int:
    cfg = get_config()

    # name -> resolved value.  Paths come out OS-normalised (back slashes on
    # Windows); ports are plain integers.  Order is cosmetic only.
    pairs = [
        # -- filesystem paths --
        ("COMFY_PY",      cfg.comfy_python),
        ("COMFY_DIR",     cfg.comfy_dir),
        ("OUTPUT_DIR",    cfg.output_dir),
        ("OLLAMA_MODELS", cfg.ollama_models_dir),
        ("OLLAMA_EXE",    cfg.ollama_exe),
        ("AIDER_PY",      cfg.aider_python),
        ("SYSTEM_PY",     cfg.system_python),
        ("TOOLS_DIR",     cfg.tools_dir),
        # -- code-RAG (local semantic code search) --
        ("RAG_PY",              cfg.rag_python),
        ("QDRANT_PATH",         cfg.qdrant_path),
        ("RAG_DATA_DIR",        cfg.rag_data_dir),
        ("FASTEMBED_CACHE_PATH", cfg.rag_cache_dir),
        ("EMBED_MODEL",         cfg.embed_model),
        ("RAG_COLLECTION",      cfg.rag_collection),
        # -- ports --
        ("COMFY_PORT",    cfg.comfy_port),
        ("WEBUI_PORT",    cfg.webui_port),
        ("RAG_PORT",      cfg.rag_port),
        ("OLLAMA_PORT",   cfg.ollama_port),
    ]

    # print() -> Windows text mode turns "\n" into CRLF, which batch for/f reads
    # cleanly.  One "set" per line.
    for name, value in pairs:
        print(_emit(name, value))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never take the launcher down with us
        print(f"[batenv] {exc}", file=sys.stderr)
        sys.exit(1)
