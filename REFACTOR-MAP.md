# REFACTOR MAP — making `studio.py` portable

This file is the **mechanical integration guide**: every hard-coded path, host
and port in `studio.py` (with its line number), and the exact `config` accessor
that should replace it. `studio.py` is intentionally **not edited yet** — do the
edits below and the GUI runs on any machine.

The line numbers refer to the current `studio.py` (1210-ish lines). If they
drift after an edit, search for the literal shown in the "Current literal"
column.

---

## 0. One-time integration header

Add near the top of `studio.py`, right after the imports (replaces lines 7–11
and 15):

```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find the vulture pkg
from vulture.config import get_config
cfg = get_config()

# --- was hard-coded, now from config.json / auto-detect ---
COMFY_PY   = cfg.comfy_python          # was r"D:\comfyui\venv\Scripts\python.exe"
COMFY_API  = cfg.comfy_api             # was "http://127.0.0.1:8188"
OUTPUT_DIR = cfg.output_dir            # was r"D:\comfyui\output"
TOOLS      = cfg.tools_dir             # was r"C:\Users\User\ai-memory-tools"
SERVICES   = cfg.services              # was the literal {name: port} dict
```

After that, every `COMFY_API`, `OUTPUT_DIR`, `COMFY_PY`, `TOOLS`, `SERVICES`
reference keeps working unchanged — only the remaining *inline literals* below
still need replacing.

---

## 1. Absolute filesystem paths (the breakers)

| Line | Current literal | Replace with |
|------|-----------------|--------------|
| 7  | `os.environ.get("LOCALAPPDATA", r"C:\Users\User\AppData\Local")` | drop the hard-coded fallback (var is unused); if needed use `cfg.ollama_exe` |
| 8  | `TOOLS = r"C:\Users\User\ai-memory-tools"` | `TOOLS = cfg.tools_dir` |
| 9  | `COMFY_PY = r"D:\comfyui\venv\Scripts\python.exe"` | `COMFY_PY = cfg.comfy_python` |
| 11 | `OUTPUT_DIR = r"D:\comfyui\output"` | `OUTPUT_DIR = cfg.output_dir` |
| 48 | `run_hidden(f'cd /d "D:\\comfyui\\ComfyUI" && "{COMFY_PY}" main.py --listen 127.0.0.1 --port 8188 --output-directory "{OUTPUT_DIR}" --cuda-device 0 --lowvram')` | `run_hidden(cfg.comfy_start_command())` — covers comfy_dir, python, host, port, output, cuda-device **and** the `--lowvram`/`--fast` flag (auto from `vram_tier`) |
| 58 | `run_hidden(r'"D:\OVRLKD-Studio\OVRLKD-KI.cmd" silent')` | `run_hidden(f'"{cfg.start_all_cmd}" silent')` |
| 64 | `run_hidden(f'"{TOOLS}\\start-webui.cmd"')` | `run_hidden(f'"{os.path.join(cfg.tools_dir, "start-webui.cmd")}"')` |
| 71 | `_open_cmd(r"D:\OVRLKD-Studio\KI-Coder.cmd")` | `_open_cmd(cfg.coder_cmd)` |
| 72 | `_open_cmd(r"D:\OVRLKD-Studio\KI-Status.cmd")` | `_open_cmd(cfg.status_cmd)` |
| 74 | `os.path.exists(r"D:\tripo3d\TripoSR\run.py")` / `_open_cmd(r"D:\tripo3d\Bild-zu-3D.cmd")` | `os.path.exists(os.path.join(cfg.tripo_src_dir, "run.py"))` / `_open_cmd(os.path.join(cfg.tripo_dir, "Bild-zu-3D.cmd"))` |
| 75 | `_open_cmd(r"D:\tripo3d\1-Setup-3D-installieren.cmd")` | `_open_cmd(os.path.join(cfg.tripo_dir, "1-Setup-3D-installieren.cmd"))` |
| 96 | `t5gguf = r"D:\comfyui\ComfyUI\models\text_encoders\t5-v1_1-xxl-encoder-Q8_0.gguf"` | `t5gguf = cfg.flux_t5_gguf_path()` |
| 138 | `inp = r"D:\comfyui\ComfyUI\input"` (img2img) | `inp = cfg.comfy_input_dir` |
| 176 | `inp = r"D:\comfyui\ComfyUI\input"` (upscale) | `inp = cfg.comfy_input_dir` |
| 213 | `inp = r"D:\comfyui\ComfyUI\input"` (face-swap) | `inp = cfg.comfy_input_dir` |
| 277 | `inp = r"D:\comfyui\ComfyUI\input"` (lip-sync) | `inp = cfg.comfy_input_dir` |
| 354–357 | `need = [ r"D:\comfyui\ComfyUI\models\unet\flux1-schnell-Q4_K_S.gguf", ...t5xxl_fp8..., ...clip_l..., ...vae\flux_ae.safetensors ]` | `need = cfg.flux_required_files()` (returns the same 4 absolute paths) |
| 569 | `os.path.exists(r"D:\tripo3d\TripoSR\run.py")` | `os.path.exists(os.path.join(cfg.tripo_src_dir, "run.py"))` |
| 570 | `_open_cmd(r"D:\tripo3d\1-Setup-3D-installieren.cmd")` | `_open_cmd(os.path.join(cfg.tripo_dir, "1-Setup-3D-installieren.cmd"))` |
| 613 | `cmd = [ r"D:\tripo3d\venv\Scripts\python.exe", "run.py", win._img, "--output-dir", r"D:\tripo3d\output", ..., "--pretrained-model-name-or-path", r"D:\tripo3d\model" ]` | `[cfg.tripo_python, "run.py", win._img, "--output-dir", cfg.tripo_output_dir, ..., cfg.tripo_model_dir]` |
| 615 | `cwd = r"D:\tripo3d\TripoSR"` | `cwd = cfg.tripo_src_dir` |
| 616 | `out = r"D:\tripo3d\output\0\mesh.obj"` | `out = os.path.join(cfg.tripo_output_dir, "0", "mesh.obj")` |
| 619 | `os.startfile(r"D:\tripo3d\output\0")` | `os.startfile(os.path.join(cfg.tripo_output_dir, "0"))` |
| 629 | `os.startfile(r"D:\tripo3d\output")` | `os.startfile(cfg.tripo_output_dir)` |

`OUTPUT_DIR` inline uses that are already fine once line 11 is changed (no edit
needed, listed for completeness): **264, 341, 487, 491, 495, 510, 579, 676, 678, 750.**

**Count: 29 hard-coded absolute Windows paths** across the lines above (plus the
`{TOOLS}\start-webui.cmd` join on line 64).

---

## 2. Host / port / URL literals

| Line | Current literal | Replace with |
|------|-----------------|--------------|
| 10  | `COMFY_API = "http://127.0.0.1:8188"` | `COMFY_API = cfg.comfy_api` |
| 15  | `SERVICES = {"Ollama":11434, "Chat/Bilder (WebUI)":8080, "ComfyUI/FLUX":8188, "Code-RAG":8001, "VPS-Tunnel":8000}` | `SERVICES = cfg.services` |
| 40  | `s.connect_ex(("127.0.0.1", p))` | `s.connect_ex((cfg.host, p))` |
| 47  | `if not port_open(8188)` | `if not port_open(cfg.comfy_port)` |
| 54  | `f"{COMFY_API}/free"` | unchanged (COMFY_API now from cfg) |
| 56  | PowerShell `-LocalPort 8188` | `-LocalPort {cfg.comfy_port}` |
| 61  | PowerShell `-LocalPort 8188,8080,8001,8000` | build from `cfg.comfy_port, cfg.webui_port, cfg.rag_port, cfg.tunnel_port` |
| 64  | `port_open(8080)` | `port_open(cfg.webui_port)` |
| 65  | `webbrowser.open("http://localhost:8080")` | `webbrowser.open(cfg.webui_url)` |
| 135, 172, 210, 274 | `if port_open(8188)` (wait loops) | `if port_open(cfg.comfy_port)` |
| 247, 256, 308, 331, 337 | `f"{COMFY_API}/prompt"` / `/history/{pid}` | unchanged (COMFY_API from cfg) |
| 298 | `"http://127.0.0.1:11434/api/generate"` | `f"{cfg.ollama_api}/api/generate"` |
| 311 | `ws.connect(f"ws://127.0.0.1:8188/ws?clientId={cid}")` | `ws.connect(f"{cfg.comfy_ws}?clientId={cid}")` |

---

## 3. Model filename literals (inside the workflow builders)

These are ComfyUI-relative filenames (resolved by ComfyUI against its models
folder). Point them at the config so a different quant/variant is a config edit,
not a code edit.

| Line | Current literal | Replace with |
|------|-----------------|--------------|
| 21  | `"flux1-schnell-Q4_K_S.gguf"` (MODELS dict) | `cfg.model_flux_unet` |
| 98  | `"t5-v1_1-xxl-encoder-Q8_0.gguf"` / `"clip_l.safetensors"` | `cfg.model_flux_t5_gguf` / `cfg.model_flux_clip_l` |
| 100 | `"t5xxl_fp8_e4m3fn.safetensors"` / `"clip_l.safetensors"` | `cfg.model_flux_t5_fp8` / `cfg.model_flux_clip_l` |
| 105 | `"vae_name": "flux_ae.safetensors"` | `cfg.model_flux_vae` |
| 106 | `"unet_name": "flux1-schnell-Q4_K_S.gguf"` | `cfg.model_flux_unet` |
| 155 | `"model_name": "4x-UltraSharp.pth"` | `cfg.model_upscale` |
| 194 | `"swap_model": "inswapper_128.onnx"` | `cfg.model_swap` |
| 202 | `SWAP_RESTORE = {... "codeformer.pth" ...}` | `cfg.model_restore` |
| 141, 179 | `"RealisticVision_v6.safetensors"` (default checkpoint for img2img/upscale) | optional: add a `models.default_checkpoint` key; for now leave as-is or use `list(MODELS.values())` |

The SD1.5 checkpoint filenames in the `MODELS` dict (lines 22–24:
`DreamShaper_v8.safetensors`, `RealisticVision_v6.safetensors`,
`ToonYou_v6.safetensors`) match the manifest `rename_to` targets, so they need
no change once the models are installed under those names.

---

## 4. Already portable (no change needed)

- Lines **648, 719, 727**: `initialdir=os.path.expanduser("~\\Desktop")` — uses
  `~`, so already user-agnostic. (Optional nicety: `os.path.join(os.path.expanduser("~"), "Desktop")`.)
- Lines 60: `taskkill /F /IM open-webui.exe` — process name, not a path.

---

## 5. The `.cmd` launchers (also hard-coded)

These live in the repo root and are opened by the GUI. They contain the same
kind of baked-in paths and must be templated too (the installer writes
`config.json`; a follow-up can generate these from it, or use `%~dp0` +
`%USERPROFILE%`).

| File | Hard-coded bits | Portable replacement |
|------|-----------------|----------------------|
| `OVRLKD-KI.cmd` | `set OLLAMA_MODELS=D:\ollama\models` (8); `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` (11, OK); `C:\Users\User\ai-memory-tools\*.cmd` (14,17,20); `D:\comfyui\venv\Scripts\python.exe` + `D:\comfyui\ComfyUI` + `D:\comfyui\output` (23–24); ports 8001/8000/8080/8188 | drive from `config.json` (`ollama_models_dir`, `tools_dir`, `comfy_*`); use `%~dp0` for repo-local files |
| `OVRLKD-Studio.cmd` | `C:\Users\User\AppData\Local\Programs\Python\Python311\pythonw.exe` (2); `D:\OVRLKD-Studio\studio.py` (2) | `%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe` (already env-based) + `"%~dp0studio.py"` (launch the studio next to the .cmd) |
| `KI-Coder.cmd` | system python `C:\Users\User\...\Python311\python.exe` (7,56); `D:\OVRLKD-Studio\auto-tune-ctx.py` + `setup-project-coding.py` (7,56); `D:\ai-coder\venv\Scripts\python.exe` (64); `%USERPROFILE%\Desktop` (43, OK) | `%~dp0` for the repo scripts; `aider_python` + `system_python` from config; `OLLAMA_API_BASE` already parameterised |
| `KI-Status.cmd` | `C:\Users\User\AppData\Local\Programs\Ollama\ollama.exe` (27); ports 8080/8188/8000/8001/11434 (32) | `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`; ports from config |

---

## 6. The other `.py` helpers (opened by KI-Coder.cmd)

| File | Line | Hard-coded | Replace with |
|------|------|-----------|--------------|
| `auto-tune-ctx.py` | 5 | `SETTINGS = r"C:\Users\User\.aider.model.settings.yml"` | `os.path.join(os.path.expanduser("~"), ".aider.model.settings.yml")` |
| `coding-orchestrator.py` | 10 | `AIDER_PY = r"D:\ai-coder\venv\Scripts\python.exe"` | `cfg.aider_python` (import the config) |
| `coding-orchestrator.py` | 9 | `OLLAMA = "http://127.0.0.1:11434"` | `cfg.ollama_api` |
| `setup-project-coding.py` | — | none (already portable) | — |

---

## Summary of what was found

- **29 hard-coded absolute Windows paths** in `studio.py` (across ~24 distinct
  targets: ComfyUI dir/venv/models/input/output, TripoSR dir/venv/model/output,
  the three `OVRLKD-*.cmd` launchers, `ai-memory-tools`).
- **~15 host/port/URL literals** in `studio.py` (127.0.0.1, localhost, ports
  8188/8080/11434/8001/8000, the ws:// URL).
- **~10 model-filename literals** in the workflow builders.
- Plus hard-coded paths in **4 `.cmd` launchers** and **2 `.py` helpers**.

Every one maps to a `vulture.config` accessor above, so the integration is
mechanical: add the header, then walk the tables.
