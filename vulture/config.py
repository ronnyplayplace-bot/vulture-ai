# -*- coding: utf-8 -*-
"""Portable configuration for Vulture AI (Overlkd Studio).

The original ``studio.py`` baked in machine-specific paths such as
``C:\\Users\\User\\ai-memory-tools`` and ``D:\\comfyui\\output``.  That breaks on
any machine that does not have a ``D:`` drive, uses a different user name or
installed the tools somewhere else.

This module removes that assumption.  A :class:`Config` object is built by
layering three sources, later ones overriding earlier ones **per key**:

1. **Built-in defaults** (:data:`DEFAULTS`) -- portable, drive-agnostic.
2. **Auto-detection** (:func:`autodetect`) -- scans every available drive for a
   ComfyUI install, an Ollama executable and a Python interpreter.
3. **A user ``config.json``** -- explicit overrides written by the user or by
   ``setup/install.py``.

Because the layers merge per key, a user only needs to specify the values that
auto-detection cannot guess.  Anything left as ``""`` (empty string) in
``config.json`` is treated as "unset" and falls back to auto-detect / default.

Public API::

    from vulture.config import get_config
    cfg = get_config()          # cached, loads config.json if present
    cfg.comfy_dir               # -> 'D:\\comfyui\\ComfyUI'
    cfg.output_dir              # -> 'D:\\comfyui\\output'
    cfg.comfy_api               # -> 'http://127.0.0.1:8188'
    cfg.comfy_start_command()   # -> full ComfyUI launch command string
    cfg.flux_required_files()   # -> [abs path, ...] for the FLUX "is it there?" check

Only the standard library is required at import time; ``nvidia-smi`` is used
opportunistically for the ``vram_tier: auto`` feature and is optional.
"""
from __future__ import annotations

import json
import os
import shutil
import string
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Locations
# --------------------------------------------------------------------------- #
# Repo root = the folder that contains studio.py (one level above this package).
REPO_ROOT: Path = Path(__file__).resolve().parent.parent

#: Filenames tried (in order) when no explicit path is passed to load_config().
CONFIG_FILENAMES = ("config.json", "vulture.config.json")


# --------------------------------------------------------------------------- #
# Built-in defaults (portable -- no drive letter, no user name)
# --------------------------------------------------------------------------- #
DEFAULTS: Dict[str, Any] = {
    "paths": {
        # Path values default to "" == unset -> filled by autodetect() or a
        # derived value at access time (e.g. comfy_models_dir = comfy_dir/models).
        "comfy_dir": "",
        "comfy_python": "",
        "comfy_models_dir": "",
        "comfy_input_dir": "",
        "output_dir": "",
        "tools_dir": "",
        "launchers_dir": "",
        "tripo_dir": "",
        "tripo_python": "",
        "tripo_src_dir": "",
        "tripo_model_dir": "",
        "tripo_output_dir": "",
        "ollama_exe": "",
        "ollama_models_dir": "",
        "system_python": "",
        "aider_python": "",
        "hf_cache_dir": "",
        "pip_cache_dir": "",
        # Code-RAG local storage (empty -> derived under _rag_base_dir()).
        "qdrant_path": "",
        "rag_data_dir": "",
    },
    "network": {
        "host": "127.0.0.1",
        "comfy_port": 8188,
        "webui_port": 8080,
        "ollama_port": 11434,
        "rag_port": 8001,
    },
    "runtime": {
        "cuda_device": 0,
        "vram_tier": "auto",
        "comfy_vram_flag": "",
        "comfy_extra_args": "",
        "enhance_model": "qwen2.5-coder:7b",
        "coder_model": "qwen2.5-coder:7b",
        # Code-RAG (local semantic search over your own projects).
        "embed_model": "BAAI/bge-small-en-v1.5",
        "rag_collection": "vulture_code",
    },
    "models": {
        "flux_unet": "flux1-schnell-Q4_K_S.gguf",
        "flux_t5_gguf": "t5-v1_1-xxl-encoder-Q8_0.gguf",
        "flux_t5_fp8": "t5xxl_fp8_e4m3fn.safetensors",
        "flux_clip_l": "clip_l.safetensors",
        "flux_vae": "flux_ae.safetensors",
        "upscale_model": "4x-UltraSharp.pth",
        "swap_model": "inswapper_128.onnx",
        "restore_model": "codeformer.pth",
    },
}

#: Human-readable service labels for the status panel (name -> port key).
SERVICE_PORT_KEYS = {
    "Ollama": "ollama_port",
    "Chat/Images (WebUI)": "webui_port",
    "ComfyUI/FLUX": "comfy_port",
    "Code-RAG": "rag_port",
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _strip_comments(obj: Any) -> Any:
    """Recursively drop keys starting with ``_`` or ``//`` (JSON "comments")."""
    if isinstance(obj, dict):
        return {
            k: _strip_comments(v)
            for k, v in obj.items()
            if not (isinstance(k, str) and (k.startswith("_") or k.startswith("//")))
        }
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``base`` deep-merged with ``over`` (``over`` wins).

    Empty-string values in ``over`` are ignored so that a ``""`` in
    ``config.json`` means "leave the lower layer's value" rather than "blank it".
    """
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        elif v == "" or v is None:
            continue  # treat "" / null as "unset" -> keep lower layer
        else:
            out[k] = v
    return out


def _available_drives() -> List[str]:
    """Return existing drive roots on Windows (``['C:\\\\', 'D:\\\\', ...]``).

    On non-Windows systems returns ``['/']`` so the scan still functions.
    """
    if os.name != "nt":
        return ["/"]
    roots = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if os.path.exists(root):
            roots.append(root)
    return roots


def _first_existing(candidates: List[str]) -> str:
    """Return the first path in ``candidates`` that exists, else ``""``."""
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return ""


def _norm(path: str) -> str:
    """Normalise a path for the host OS (forward slashes -> backslashes on nt).

    Empty strings pass through unchanged.
    """
    if not path:
        return ""
    return os.path.normpath(os.path.expandvars(os.path.expanduser(str(path))))


def _rag_base_dir() -> str:
    """Drive-agnostic base folder for the local code-RAG's private data.

    Everything the RAG writes -- the embedded Qdrant store, the project registry
    and the fastembed model cache -- lives under here.  Uses ``%LOCALAPPDATA%``
    on Windows and ``~/.local/share`` elsewhere, so no drive letter or user name
    is baked in and nothing is written into the repo.  The individual folders can
    still be redirected via the ``qdrant_path`` / ``rag_data_dir`` config keys.
    """
    base = os.environ.get("LOCALAPPDATA", "") if os.name == "nt" else ""
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "VultureAI", "rag")


# --------------------------------------------------------------------------- #
# Auto-detection
# --------------------------------------------------------------------------- #
def _detect_comfy_dir(drives: List[str]) -> str:
    """Find a ComfyUI application folder (contains ``main.py`` + ``models``)."""
    home = os.path.expanduser("~")
    rel = [
        r"comfyui\ComfyUI",
        r"ComfyUI",
        r"ComfyUI_windows_portable\ComfyUI",
        r"AI\ComfyUI",
        r"ai\comfyui\ComfyUI",
        r"apps\comfyui\ComfyUI",
        r"StabilityMatrix\Packages\ComfyUI",
    ]
    candidates: List[str] = []
    for d in drives:
        candidates += [os.path.join(d, r) for r in rel]
    candidates += [
        os.path.join(home, "ComfyUI"),
        os.path.join(home, "Desktop", "ComfyUI"),
        os.path.join(home, "Documents", "ComfyUI"),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "main.py")):
            return c
    return ""


def _detect_comfy_python(comfy_dir: str) -> str:
    """Find the Python interpreter that runs a given ComfyUI install."""
    if not comfy_dir:
        return ""
    parent = os.path.dirname(comfy_dir)
    candidates = [
        os.path.join(parent, "venv", "Scripts", "python.exe"),
        os.path.join(comfy_dir, "venv", "Scripts", "python.exe"),
        os.path.join(comfy_dir, ".venv", "Scripts", "python.exe"),
        os.path.join(parent, "python_embeded", "python.exe"),          # portable build
        os.path.join(os.path.dirname(parent), "python_embeded", "python.exe"),
        # POSIX venvs (for completeness on non-Windows)
        os.path.join(parent, "venv", "bin", "python"),
        os.path.join(comfy_dir, "venv", "bin", "python"),
    ]
    return _first_existing(candidates)


def _detect_ollama_exe(drives: List[str]) -> str:
    """Locate ``ollama`` (or ``ollama.exe``)."""
    which = shutil.which("ollama")
    if which:
        return which
    localappdata = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if localappdata:
        candidates.append(os.path.join(localappdata, "Programs", "Ollama", "ollama.exe"))
    candidates += [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Ollama", "ollama.exe"),
    ]
    for d in drives:
        candidates.append(os.path.join(d, "ollama", "ollama.exe"))
    return _first_existing(candidates)


def _detect_ollama_models(drives: List[str]) -> str:
    """Locate the Ollama models directory."""
    env = os.environ.get("OLLAMA_MODELS")
    if env and os.path.exists(env):
        return env
    home_default = os.path.join(os.path.expanduser("~"), ".ollama", "models")
    candidates = [home_default] + [os.path.join(d, "ollama", "models") for d in drives]
    return _first_existing(candidates)


def _detect_system_python() -> str:
    """Best-effort path to a usable system Python 3.11."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if localappdata:
        candidates += [
            os.path.join(localappdata, "Programs", "Python", "Python311", "python.exe"),
        ]
    candidates += [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "Python311", "python.exe"),
        shutil.which("python") or "",
        shutil.which("python3") or "",
        sys.executable or "",
    ]
    return _first_existing(candidates)


def _detect_tripo(drives: List[str]) -> Dict[str, str]:
    """Locate an optional TripoSR (Image->3D) install."""
    for d in drives:
        base = os.path.join(d, "tripo3d")
        if os.path.exists(os.path.join(base, "TripoSR", "run.py")):
            return {
                "tripo_dir": base,
                "tripo_src_dir": os.path.join(base, "TripoSR"),
                "tripo_python": _first_existing(
                    [os.path.join(base, "venv", "Scripts", "python.exe")]
                ),
                "tripo_model_dir": os.path.join(base, "model"),
                "tripo_output_dir": os.path.join(base, "output"),
            }
    return {}


def _detect_aider_python(drives: List[str]) -> str:
    """Locate the Python of an optional Aider coding-agent venv.

    Mirrors the ``ai-coder\\venv`` layout the Overlkd-Coder launcher expects; falls
    back to a few common variants so a fresh clone finds it without editing
    ``config.json``.
    """
    home = os.path.expanduser("~")
    rel = [
        r"ai-coder\venv\Scripts\python.exe",
        r"ai-coder\.venv\Scripts\python.exe",
        r"aider\venv\Scripts\python.exe",
    ]
    candidates: List[str] = []
    for d in drives:
        candidates += [os.path.join(d, r) for r in rel]
    candidates += [
        os.path.join(home, "ai-coder", "venv", "Scripts", "python.exe"),
        # POSIX venvs (for completeness on non-Windows)
        *[os.path.join(d, "ai-coder", "venv", "bin", "python") for d in drives],
    ]
    return _first_existing(candidates)


def _detect_tools_dir(drives: List[str]) -> str:
    """Locate the optional ``ai-memory-tools`` folder (WebUI / Code-RAG launchers)."""
    home = os.path.expanduser("~")
    candidates = [os.path.join(home, "ai-memory-tools")]
    for d in drives:
        candidates += [
            os.path.join(d, "ai-memory-tools"),
            os.path.join(d, "Overlkd", "apps", "ai-memory-tools"),
        ]
    return _first_existing(candidates)


def autodetect() -> Dict[str, Any]:
    """Scan the machine and return a partial config with everything found.

    Only keys that were actually located are included, so this dict is safe to
    merge *over* :data:`DEFAULTS` and *under* the user's ``config.json``.
    """
    drives = _available_drives()
    paths: Dict[str, str] = {}

    comfy_dir = _detect_comfy_dir(drives)
    if comfy_dir:
        paths["comfy_dir"] = comfy_dir
        paths["comfy_python"] = _detect_comfy_python(comfy_dir)
        paths["comfy_models_dir"] = os.path.join(comfy_dir, "models")
        paths["comfy_input_dir"] = os.path.join(comfy_dir, "input")
        default_out = os.path.join(os.path.dirname(comfy_dir), "output")
        paths["output_dir"] = default_out if os.path.exists(default_out) else os.path.join(comfy_dir, "output")

    ollama_exe = _detect_ollama_exe(drives)
    if ollama_exe:
        paths["ollama_exe"] = ollama_exe
    ollama_models = _detect_ollama_models(drives)
    if ollama_models:
        paths["ollama_models_dir"] = ollama_models

    sys_py = _detect_system_python()
    if sys_py:
        paths["system_python"] = sys_py

    aider_py = _detect_aider_python(drives)
    if aider_py:
        paths["aider_python"] = aider_py

    tools = _detect_tools_dir(drives)
    if tools:
        paths["tools_dir"] = tools

    paths.update(_detect_tripo(drives))

    # Drop empties so they don't override lower layers.
    paths = {k: v for k, v in paths.items() if v}
    return {"paths": paths}


# --------------------------------------------------------------------------- #
# GPU / VRAM tier
# --------------------------------------------------------------------------- #
def query_gpu() -> Optional[Dict[str, float]]:
    """Return ``{'vram_gb': float, 'compute_cap': float}`` via nvidia-smi, or None."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,compute_cap",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip().splitlines()
        if not out:
            return None
        mem_mib, cap = out[0].split(",")
        return {"vram_gb": float(mem_mib) / 1024.0, "compute_cap": float(cap)}
    except Exception:
        return None


def _tier_from_vram(vram_gb: float) -> str:
    if vram_gb <= 7:
        return "s"
    if vram_gb <= 13:
        return "m"
    if vram_gb <= 17:
        return "l"
    return "xl"


# --------------------------------------------------------------------------- #
# Config object
# --------------------------------------------------------------------------- #
class Config:
    """Typed, read-only view over the merged configuration dictionary.

    Construct via :func:`load_config` / :func:`get_config` rather than directly.
    All filesystem accessors return OS-normalised absolute-ish paths (forward
    slashes in the JSON are converted to back slashes on Windows).
    """

    def __init__(self, data: Dict[str, Any], source: str = "<merged>") -> None:
        self._d = data
        self.source = source  #: where the user overrides came from ("<defaults>", path, ...)

    # -- low level -------------------------------------------------------- #
    def raw(self) -> Dict[str, Any]:
        """Return the underlying merged dict (a copy)."""
        return json.loads(json.dumps(self._d))

    def _p(self, key: str) -> str:
        return str(self._d.get("paths", {}).get(key, "") or "")

    def _n(self, key: str) -> Any:
        return self._d.get("network", {}).get(key)

    def _r(self, key: str) -> Any:
        return self._d.get("runtime", {}).get(key)

    def _m(self, key: str) -> str:
        return str(self._d.get("models", {}).get(key, "") or "")

    # -- paths ------------------------------------------------------------ #
    @property
    def comfy_dir(self) -> str:
        """ComfyUI application folder (contains ``main.py``)."""
        return _norm(self._p("comfy_dir"))

    @property
    def comfy_python(self) -> str:
        """Python interpreter for the ComfyUI venv (falls back to sys.executable)."""
        return _norm(self._p("comfy_python") or sys.executable)

    @property
    def comfy_models_dir(self) -> str:
        """Models folder; derived as ``comfy_dir/models`` when not set."""
        v = self._p("comfy_models_dir")
        if not v and self.comfy_dir:
            v = os.path.join(self.comfy_dir, "models")
        return _norm(v)

    @property
    def comfy_custom_nodes_dir(self) -> str:
        """``comfy_dir/custom_nodes``."""
        return _norm(os.path.join(self.comfy_dir, "custom_nodes")) if self.comfy_dir else ""

    @property
    def comfy_input_dir(self) -> str:
        """Input folder; derived as ``comfy_dir/input`` when not set."""
        v = self._p("comfy_input_dir")
        if not v and self.comfy_dir:
            v = os.path.join(self.comfy_dir, "input")
        return _norm(v)

    @property
    def output_dir(self) -> str:
        """Generated-media output folder; derived from ``comfy_dir`` when unset."""
        v = self._p("output_dir")
        if not v and self.comfy_dir:
            v = os.path.join(os.path.dirname(self.comfy_dir), "output")
        return _norm(v)

    @property
    def tools_dir(self) -> str:
        """Optional ``ai-memory-tools`` folder (WebUI / Code-RAG launchers)."""
        return _norm(self._p("tools_dir"))

    @property
    def launchers_dir(self) -> str:
        """Folder holding the ``.cmd`` launchers; defaults to the repo root."""
        return _norm(self._p("launchers_dir") or str(REPO_ROOT))

    @property
    def tripo_dir(self) -> str:
        return _norm(self._p("tripo_dir"))

    @property
    def tripo_python(self) -> str:
        return _norm(self._p("tripo_python"))

    @property
    def tripo_src_dir(self) -> str:
        return _norm(self._p("tripo_src_dir"))

    @property
    def tripo_model_dir(self) -> str:
        return _norm(self._p("tripo_model_dir"))

    @property
    def tripo_output_dir(self) -> str:
        return _norm(self._p("tripo_output_dir"))

    @property
    def ollama_exe(self) -> str:
        return _norm(self._p("ollama_exe"))

    @property
    def ollama_models_dir(self) -> str:
        return _norm(self._p("ollama_models_dir"))

    @property
    def system_python(self) -> str:
        return _norm(self._p("system_python") or sys.executable)

    @property
    def aider_python(self) -> str:
        return _norm(self._p("aider_python"))

    @property
    def hf_cache_dir(self) -> str:
        return _norm(self._p("hf_cache_dir"))

    @property
    def pip_cache_dir(self) -> str:
        return _norm(self._p("pip_cache_dir"))

    # -- code-RAG (local, private semantic code search) ------------------- #
    @property
    def qdrant_path(self) -> str:
        """Embedded-Qdrant store for the code-RAG; derived under the RAG base
        folder when not set.  This is a local path, never a Qdrant server."""
        v = self._p("qdrant_path")
        if not v:
            v = os.path.join(_rag_base_dir(), "qdrant")
        return _norm(v)

    @property
    def rag_data_dir(self) -> str:
        """Folder for the RAG project registry; derived under the RAG base
        folder when not set."""
        v = self._p("rag_data_dir")
        if not v:
            v = os.path.join(_rag_base_dir(), "data")
        return _norm(v)

    @property
    def rag_cache_dir(self) -> str:
        """fastembed model cache; kept next to :attr:`rag_data_dir`."""
        return _norm(os.path.join(os.path.dirname(self.rag_data_dir), "cache"))

    @property
    def rag_python(self) -> str:
        """Interpreter that runs the RAG server: its dedicated venv (created by
        ``setup/install.py``) when present, otherwise the system Python."""
        base = _rag_base_dir()
        candidates = [
            os.path.join(base, "venv", "Scripts", "python.exe"),  # Windows
            os.path.join(base, "venv", "bin", "python"),          # POSIX
        ]
        found = _first_existing(candidates)
        return _norm(found) if found else self.system_python

    # -- launcher files (resolved against launchers_dir) ------------------ #
    def launcher(self, filename: str) -> str:
        """Absolute path to a ``.cmd`` launcher inside :attr:`launchers_dir`."""
        return _norm(os.path.join(self.launchers_dir, filename))

    @property
    def start_all_cmd(self) -> str:
        return self.launcher("Overlkd-Start.cmd")

    @property
    def coder_cmd(self) -> str:
        return self.launcher("Overlkd-Coder.cmd")

    @property
    def status_cmd(self) -> str:
        return self.launcher("Overlkd-Status.cmd")

    # -- network ---------------------------------------------------------- #
    @property
    def host(self) -> str:
        return str(self._n("host") or "127.0.0.1")

    @property
    def comfy_port(self) -> int:
        return int(self._n("comfy_port"))

    @property
    def webui_port(self) -> int:
        return int(self._n("webui_port"))

    @property
    def ollama_port(self) -> int:
        return int(self._n("ollama_port"))

    @property
    def rag_port(self) -> int:
        return int(self._n("rag_port"))

    @property
    def comfy_api(self) -> str:
        """HTTP base URL of the ComfyUI API, e.g. ``http://127.0.0.1:8188``."""
        return f"http://{self.host}:{self.comfy_port}"

    @property
    def comfy_ws(self) -> str:
        """WebSocket base URL of the ComfyUI API (append ``?clientId=...``)."""
        return f"ws://{self.host}:{self.comfy_port}/ws"

    @property
    def ollama_api(self) -> str:
        """HTTP base URL of the Ollama API, e.g. ``http://127.0.0.1:11434``."""
        return f"http://{self.host}:{self.ollama_port}"

    @property
    def webui_url(self) -> str:
        """Browser URL for Open WebUI (chat)."""
        return f"http://localhost:{self.webui_port}"

    @property
    def rag_api(self) -> str:
        """HTTP base URL of the local code-RAG server, e.g. ``http://127.0.0.1:8001``."""
        return f"http://{self.host}:{self.rag_port}"

    @property
    def services(self) -> Dict[str, int]:
        """``{label: port}`` mapping for the status panel."""
        return {label: int(self._n(pk)) for label, pk in SERVICE_PORT_KEYS.items()}

    # -- runtime ---------------------------------------------------------- #
    @property
    def cuda_device(self) -> int:
        return int(self._r("cuda_device") or 0)

    @property
    def vram_tier(self) -> str:
        """Resolved VRAM tier (``s``/``m``/``l``/``xl``); resolves ``auto`` live."""
        tier = str(self._r("vram_tier") or "auto").lower()
        if tier in ("s", "m", "l", "xl"):
            return tier
        gpu = query_gpu()
        if gpu:
            return _tier_from_vram(gpu["vram_gb"])
        return "s"  # safe fallback: assume a 6GB card

    @property
    def comfy_vram_flag(self) -> str:
        """ComfyUI memory flag; derived from :attr:`vram_tier` when not overridden."""
        override = str(self._r("comfy_vram_flag") or "").strip()
        if override:
            return override
        return "--lowvram" if self.vram_tier == "s" else "--fast"

    @property
    def comfy_extra_args(self) -> str:
        return str(self._r("comfy_extra_args") or "").strip()

    @property
    def enhance_model(self) -> str:
        return str(self._r("enhance_model") or "qwen2.5-coder:7b")

    @property
    def coder_model(self) -> str:
        return str(self._r("coder_model") or "qwen2.5-coder:7b")

    @property
    def embed_model(self) -> str:
        """fastembed model name used by the code-RAG (CPU, ONNX)."""
        return str(self._r("embed_model") or "BAAI/bge-small-en-v1.5")

    @property
    def rag_collection(self) -> str:
        """Qdrant collection name the code-RAG indexes into."""
        return str(self._r("rag_collection") or "vulture_code")

    # -- model filenames -------------------------------------------------- #
    @property
    def model_flux_unet(self) -> str:
        return self._m("flux_unet")

    @property
    def model_flux_t5_gguf(self) -> str:
        return self._m("flux_t5_gguf")

    @property
    def model_flux_t5_fp8(self) -> str:
        return self._m("flux_t5_fp8")

    @property
    def model_flux_clip_l(self) -> str:
        return self._m("flux_clip_l")

    @property
    def model_flux_vae(self) -> str:
        return self._m("flux_vae")

    @property
    def model_upscale(self) -> str:
        return self._m("upscale_model")

    @property
    def model_swap(self) -> str:
        return self._m("swap_model")

    @property
    def model_restore(self) -> str:
        return self._m("restore_model")

    # -- convenience ------------------------------------------------------ #
    def models_subdir(self, *parts: str) -> str:
        """Absolute path inside the ComfyUI models folder."""
        return _norm(os.path.join(self.comfy_models_dir, *parts))

    def flux_required_files(self) -> List[str]:
        """Absolute paths of the four files FLUX needs (unet, t5, clip_l, vae).

        Mirrors the check ``studio.py`` performs before starting a FLUX render.
        """
        return [
            self.models_subdir("unet", self.model_flux_unet),
            self.models_subdir("text_encoders", self.model_flux_t5_fp8),
            self.models_subdir("text_encoders", self.model_flux_clip_l),
            self.models_subdir("vae", self.model_flux_vae),
        ]

    def flux_t5_gguf_path(self) -> str:
        """Absolute path of the optional Q8 T5 GGUF encoder (better on Pascal)."""
        return self.models_subdir("text_encoders", self.model_flux_t5_gguf)

    def comfy_start_command(self, output_dir: Optional[str] = None) -> str:
        """Build the shell command that ``ensure_comfy()`` uses to launch ComfyUI."""
        out = _norm(output_dir) if output_dir else self.output_dir
        extra = (self.comfy_vram_flag + " " + self.comfy_extra_args).strip()
        return (
            f'cd /d "{self.comfy_dir}" && "{self.comfy_python}" main.py '
            f"--listen {self.host} --port {self.comfy_port} "
            f'--output-directory "{out}" --cuda-device {self.cuda_device} {extra}'
        ).strip()

    def ollama_env(self) -> Dict[str, str]:
        """Environment overlay that points Ollama at :attr:`ollama_models_dir`."""
        env = {}
        if self.ollama_models_dir:
            env["OLLAMA_MODELS"] = self.ollama_models_dir
        return env

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Config(source={self.source!r}, comfy_dir={self.comfy_dir!r}, "
            f"output_dir={self.output_dir!r}, comfy_api={self.comfy_api!r})"
        )


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def _find_config_file(explicit: Optional[str]) -> str:
    """Resolve which ``config.json`` to load (explicit > env > repo root)."""
    if explicit:
        return explicit if os.path.exists(explicit) else ""
    env = os.environ.get("VULTURE_CONFIG")
    if env and os.path.exists(env):
        return env
    for name in CONFIG_FILENAMES:
        candidate = REPO_ROOT / name
        if candidate.exists():
            return str(candidate)
    return ""


def load_config(path: Optional[str] = None, *, use_autodetect: bool = True) -> Config:
    """Build a :class:`Config` by layering defaults, auto-detection and file.

    Args:
        path: explicit path to a ``config.json``. If ``None``, the loader checks
            ``$VULTURE_CONFIG`` and then the repo root.
        use_autodetect: set ``False`` to skip the drive scan (faster, tests).

    Returns:
        A fully-merged :class:`Config`. Never raises for a missing/invalid file;
        it logs a note to stderr and continues with defaults + auto-detect.
    """
    merged: Dict[str, Any] = json.loads(json.dumps(DEFAULTS))  # deep copy

    if use_autodetect:
        try:
            merged = _deep_merge(merged, autodetect())
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[vulture.config] auto-detect skipped: {exc}", file=sys.stderr)

    source = "<defaults+autodetect>"
    cfg_file = _find_config_file(path)
    if cfg_file:
        try:
            with open(cfg_file, "r", encoding="utf-8") as fh:
                user = _strip_comments(json.load(fh))
            merged = _deep_merge(merged, user)
            source = cfg_file
        except Exception as exc:
            print(
                f"[vulture.config] could not read {cfg_file}: {exc} "
                f"-- using defaults + auto-detect",
                file=sys.stderr,
            )

    return Config(merged, source=source)


# Module-level cache so repeated get_config() calls are cheap.
_CACHED: Optional[Config] = None


def get_config(reload: bool = False) -> Config:
    """Return a process-wide cached :class:`Config` (loads on first call).

    Args:
        reload: force a fresh load (e.g. after the user edited ``config.json``).
    """
    global _CACHED
    if _CACHED is None or reload:
        _CACHED = load_config()
    return _CACHED


# --------------------------------------------------------------------------- #
# CLI: `python -m vulture.config` prints the resolved configuration.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    cfg = load_config()
    print(f"# Vulture AI resolved configuration  (overrides from: {cfg.source})\n")
    rows = [
        ("comfy_dir", cfg.comfy_dir),
        ("comfy_python", cfg.comfy_python),
        ("comfy_models_dir", cfg.comfy_models_dir),
        ("comfy_custom_nodes_dir", cfg.comfy_custom_nodes_dir),
        ("comfy_input_dir", cfg.comfy_input_dir),
        ("output_dir", cfg.output_dir),
        ("tools_dir", cfg.tools_dir),
        ("launchers_dir", cfg.launchers_dir),
        ("ollama_exe", cfg.ollama_exe),
        ("ollama_models_dir", cfg.ollama_models_dir),
        ("system_python", cfg.system_python),
        ("aider_python", cfg.aider_python),
        ("tripo_dir", cfg.tripo_dir),
        ("host", cfg.host),
        ("comfy_api", cfg.comfy_api),
        ("comfy_ws", cfg.comfy_ws),
        ("ollama_api", cfg.ollama_api),
        ("webui_url", cfg.webui_url),
        ("rag_api", cfg.rag_api),
        ("rag_python", cfg.rag_python),
        ("qdrant_path", cfg.qdrant_path),
        ("rag_data_dir", cfg.rag_data_dir),
        ("embed_model", cfg.embed_model),
        ("rag_collection", cfg.rag_collection),
        ("vram_tier", cfg.vram_tier),
        ("comfy_vram_flag", cfg.comfy_vram_flag),
        ("enhance_model", cfg.enhance_model),
    ]
    width = max(len(k) for k, _ in rows)
    for k, v in rows:
        print(f"{k.ljust(width)} : {v}")
    print("\n# FLUX files checked before rendering:")
    for p in cfg.flux_required_files():
        mark = "OK " if os.path.exists(p) else "-- "
        print(f"  [{mark}] {p}")
    print("\n# ComfyUI start command:")
    print("  " + cfg.comfy_start_command())
