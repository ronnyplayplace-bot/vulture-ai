# Bootstrap — full "fresh clone → it runs" flow

This document describes exactly how Vulture AI rebuilds a **complete** working
environment from nothing, and the checklist to prove it.

**Acceptance test:** delete everything → `git clone` → `python setup/install.py`
→ `python setup/verify.py` reports OK → `python studio.py` runs.

---

## What the user must have BEFORE the bootstrap

The installer builds the software environment and downloads models, but it does
**not** install system-level tools. The user provides:

- **Python 3.11** (64-bit, on PATH)
- **Git** (on PATH)
- **NVIDIA driver** + a CUDA-capable GPU (the venv installs the `cu121` torch build)
- **Ollama** desktop app (from ollama.com) — the installer calls `ollama pull`
- **~100 GB free disk** on the drive where ComfyUI/models will live
- Internet access (HuggingFace, GitHub, the Ollama registry)

Everything else is created by `setup/install.py`.

---

## What lives in the repo (committed) vs. what the installer fetches

**In the repo (small, no weights):**

```
studio.py                    the GUI (paths come from vulture.config)
config.example.json          config template (copy -> config.json to override)
vulture/__init__.py
vulture/config.py            loader: defaults <- auto-detect <- config.json
setup/install.py             the bootstrap (this doc's subject)
setup/verify.py              self-test
setup/models.manifest.json   what to install (ComfyUI, nodes, models, LLMs)
setup/README-SETUP.md        user quick-start
setup/BOOTSTRAP.md           this file
REFACTOR-MAP.md              how studio.py maps onto config
Overlkd-*.cmd                launchers
rtx-setup/*.cmd              optional RTX-era upgrade waves
```

The `.gitignore` already blocks weights (`*.safetensors`, `*.gguf`, `*.pth`,
`*.onnx`, `models/`), so the repo stays small and nothing personal is committed.

**Fetched by the installer (large, into the user's folders):**

- ComfyUI itself + its venv + `cu121` torch + ComfyUI requirements
- custom nodes (ComfyUI-GGUF, UltimateSDUpscale, ReActor, LivePortraitKJ,
  VideoHelperSuite; optional KJNodes/LTX/Wan/etc.)
- model files (FLUX schnell GGUF + t5xxl + clip_l + flux VAE, SD1.5 checkpoints,
  4x-UltraSharp, ReActor inswapper_128 + buffalo_l, CodeFormer, LivePortrait)
- Ollama models (`qwen2.5-coder:7b` required; others optional)

---

## The bootstrap steps (order matters)

`python setup/install.py` runs these in sequence. Each is **idempotent** and
**resumable** — rerun any time; present items are skipped, partial downloads
continue.

### Step 1 — `comfyui`
- If no ComfyUI is found (auto-detect scans all drives), pick an install
  location (most-free non-system drive, or `--comfy-dir`), `git clone` ComfyUI.
- Create a sibling `venv` with the user's Python 3.11.
- `pip install` the pinned `cu121` torch trio, then ComfyUI `requirements.txt`.
- Create `output/` and `input/` folders.

### Step 2 — `nodes`
- `git clone` each **required** custom node into `custom_nodes/` (add `--all`
  for the optional ones), then `pip install -r requirements.txt` per node.
- **Then re-force `numpy==1.26.4`.** This is critical and must come *after* the
  node installs: mediapipe (LivePortrait) and insightface (ReActor) pull newer
  numpy, which breaks both. The pin is in the manifest's `pip_pins`.

### Step 3 — `models`
- Ensure `huggingface_hub` / `requests` / `tqdm` are available (installs them if
  not).
- For each manifest model: resolve its target path, skip if present (>1 MB),
  else download from the original source:
  - `hf_file` → `huggingface_hub.hf_hub_download` (auto-resume, progress)
  - `hf_snapshot` → `snapshot_download` (whole repo, e.g. LivePortrait weights)
  - `url` → streaming `requests` download with HTTP-range **resume** + `tqdm`
    bar; `extract: zip` entries are unzipped (buffalo_l)
- `rename_to` handles files whose repo name differs from the ComfyUI name.

### Step 4 — `ollama`
- Point `OLLAMA_MODELS` at the configured folder, `ollama list` to see what's
  there, `ollama pull` the missing required (and, with `--all`, optional) tags.

### Step 5 — `config`
- Write `config.json` in the repo root with the resolved paths (ComfyUI dir,
  venv python, output dir, Ollama, system python). Existing user values are
  kept; only gaps are filled. This is what makes `studio.py` portable.

Then it prints a summary and points you at `verify.py`.

---

## Fresh-clone test checklist

Run this to confirm the acceptance test on a clean machine (or a throwaway VM):

- [ ] Python 3.11, Git, NVIDIA driver, Ollama app installed; ~100 GB free
- [ ] `git clone <repo>` and `cd` into it
- [ ] `python setup/install.py --list` — sanity: shows *everything missing*, downloads nothing
- [ ] `python setup/install.py` (or `--all`) — runs the 5 steps; watch for
      `[FAIL]` lines (gated HF repo? insightface wheel? bad Ollama tag?)
- [ ] `python -m vulture.config` — paths point at the new install, not `D:\...`
- [ ] `python setup/verify.py` — required checks all `OK`, exit code 0
- [ ] `python setup/verify.py --start-comfy` — ComfyUI boots, port opens, the 5
      key node class types register (`UnetLoaderGGUF`, `UltimateSDUpscale`,
      `ReActorFaceSwap`, `LivePortraitProcess`, `VHS_LoadVideo`)
- [ ] `python studio.py` — window opens, "START ALL", generate one FLUX image
- [ ] rerun `python setup/install.py` — proves idempotency: **all `[skip]`**

### Known manual follow-ups (documented, not silent failures)

- **FLUX VAE** may be gated → `huggingface-cli login` + accept the licence, re-run.
- **ReActor / InsightFace** may need the prebuilt `cp311` wheel from
  `github.com/Gourieff/Assets` if pip can't build it.
- **Ollama `qwen3.5:*`** tags are optional; if a tag isn't in the registry on
  your date, keep `qwen2.5-coder:7b` as the coder model (it's the required one).

---

## Design notes

- **Idempotent & non-destructive:** the installer only clones/pulls/downloads
  what's missing and never deletes. Safe to interrupt and rerun.
- **Read-only modes:** `--list` and `--dry-run` make no changes at all (no
  clone, no pip, no write) — use them to inspect first.
- **One source of truth:** `studio.py`, `install.py` and `verify.py` all read
  paths from `vulture.config`, so there's no second place to update.
- **Light deps:** only `huggingface_hub`, `requests`, `tqdm` beyond the stdlib,
  and only for the download step.
