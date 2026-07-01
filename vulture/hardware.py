# -*- coding: utf-8 -*-
"""Hardware detection helpers for the Vulture AI Studio "Setup / install" panel.

Pure-stdlib and Windows-first. ``studio.py`` uses these to show the detected
GPU / RAM in the Setup window and to scale the rough model speed estimates
against a **GTX 1060 6GB baseline (multiplier = 1.0)**.

Public API::

    detect_gpu()        -> {"name": str, "vram_gb": float}
    detect_ram_gb()     -> float
    speed_multiplier(vram_gb, gpu_name) -> float
"""
import subprocess, ctypes

_NO_WINDOW = 0x08000000  # subprocess.CREATE_NO_WINDOW (avoid a console flash)


def detect_gpu() -> dict:
    """Return ``{"name": str, "vram_gb": float}`` for the primary NVIDIA GPU.

    Queries ``nvidia-smi``. When no NVIDIA GPU / driver is present the name is
    an empty string and ``vram_gb`` is ``0.0`` (the caller then shows a
    CPU-mode note)."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW)
        lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
        if r.returncode == 0 and lines:
            parts = lines[0].split(",")
            name = parts[0].strip()
            vram_gb = round(float(parts[1].strip()) / 1024.0, 1) if len(parts) > 1 else 0.0
            return {"name": name, "vram_gb": vram_gb}
    except Exception:
        pass
    return {"name": "", "vram_gb": 0.0}


def detect_ram_gb() -> float:
    """Total physical RAM in GB (Windows). Tries ``GlobalMemoryStatusEx``
    first, then falls back to ``wmic``, then ``0.0`` if both fail."""
    try:
        class _MEMSTAT(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = _MEMSTAT()
        stat.dwLength = ctypes.sizeof(_MEMSTAT)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return round(stat.ullTotalPhys / (1024 ** 3), 1)
    except Exception:
        pass
    try:
        r = subprocess.run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
                           capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW)
        for tok in (r.stdout or "").split():
            if tok.isdigit():
                return round(int(tok) / (1024 ** 3), 1)
    except Exception:
        pass
    return 0.0


# GPU-name substring -> rough speed multiplier vs a GTX 1060 6GB (= 1.0).
# Matched case-insensitively; the LONGEST matching substring wins so that e.g.
# "rtx 3060 ti" beats "rtx 3060".
_GPU_MULT = {
    "rtx 5090": 13.0, "rtx 5080": 8.0, "rtx 5070": 5.5,
    "rtx 4090": 9.0, "rtx 4080": 6.5, "rtx 4070": 4.2, "rtx 4060": 2.8,
    "rtx 3090": 5.5, "rtx 3080": 4.8, "rtx 3070": 3.6,
    "rtx 3060 ti": 3.2, "rtx 3060": 2.6,
    "rtx 2060": 1.8,
    "gtx 1080 ti": 1.9, "gtx 1060": 1.0,
}


def speed_multiplier(vram_gb: float, gpu_name: str) -> float:
    """Rough speed multiplier vs a GTX 1060 6GB baseline (1.0).

    Matches ``gpu_name`` by substring (case-insensitive, most specific wins).
    Unknown NVIDIA cards are estimated from VRAM; no GPU -> CPU-only (0.15)."""
    name = (gpu_name or "").lower()
    if not name or not vram_gb or vram_gb <= 0:
        return 0.15  # CPU-only, very slow
    best = None
    for sub, mult in _GPU_MULT.items():
        if sub in name and (best is None or len(sub) > len(best[0])):
            best = (sub, mult)
    if best:
        return best[1]
    # Unknown card: estimate from VRAM (very rough)
    return round(max(1.0, vram_gb / 6.0 * 1.3), 2)
