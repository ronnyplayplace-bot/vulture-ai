# Vulture AI — Setup

Get Vulture AI (Overlkd Studio) running on your own machine. Everything is
offline; the models are downloaded from their original sources into **your**
folders — nothing is bundled and nothing leaves your PC.

## 1. Prerequisites (install these first)

| Need | Why | Get it |
|------|-----|--------|
| **Windows 10/11** | the launcher is Windows-first | — |
| **Python 3.11** (64-bit) | runs the studio + installer | python.org — tick "Add to PATH" |
| **Git** | clones ComfyUI + custom nodes | git-scm.com |
| **NVIDIA GPU + current driver + CUDA-capable** | image & video generation | GeForce/Studio driver |
| **Ollama** (desktop app) | local LLMs (chat, prompt optimiser, coding) | ollama.com |
| **~100 GB free disk** | the models are big — put them on a roomy drive | — |

> A 6 GB card (GTX 1060) works but is slow; 12 GB (RTX 3060) is the comfortable
> target. Keep the big models off your system drive if `C:` is small.

## 2. Get the code

```bat
git clone https://github.com/<you>/vulture-ai.git
cd vulture-ai
```

## 3. Run the installer

```bat
python setup/install.py            :: required models + nodes
:: or, to also grab the optional extras (SD1.5 styles, face-restore, etc.):
python setup/install.py --all
```

The installer is **idempotent** — run it as often as you like; it skips anything
already present and resumes interrupted downloads. It will, in order:

1. install **ComfyUI** + its `cu121` virtual environment (if missing),
2. clone the **custom nodes** the studio needs and pin `numpy==1.26.4`,
3. download only the **missing model files** (FLUX, SD1.5, upscaler, face-swap,
   LivePortrait, …),
4. `ollama pull` the **LLMs**,
5. write a **`config.json`** with the paths it resolved.

Useful flags:

```bat
python setup/install.py --list        :: show what's present/missing, download nothing
python setup/install.py --dry-run     :: print the plan only
python setup/install.py --steps models   :: just (re)download model files
python setup/install.py --comfy-dir E:\AI\ComfyUI   :: choose where ComfyUI goes
```

## 4. Verify

```bat
python setup/verify.py            :: OK/FAIL checklist for the whole install
python setup/verify.py --start-comfy   :: also boot ComfyUI and confirm nodes load
```

Exit code is `0` when all required checks pass.

## 5. Start the studio

```bat
python studio.py
:: or double-click Overlkd-Studio.cmd
```

## Configuration

You normally don't need to touch anything — the loader auto-detects ComfyUI,
Ollama and Python across your drives. To override, copy
[`config.example.json`](../config.example.json) to `config.json` in the repo
root and edit the values (drive letters, ports, VRAM tier, …). Any key you leave
as `""` falls back to auto-detection.

See what got resolved:

```bat
python -m vulture.config
```

## Gated / licensed models

- The **FLUX VAE** (`ae.safetensors`) may need a one-time
  `huggingface-cli login` and licence acceptance. The installer tells you if a
  download is gated.
- **InsightFace** (face-swap: `inswapper_128`, `buffalo_l`) and **CodeFormer**
  are **non-commercial / research use only**. SD1.5 checkpoints are
  CreativeML OpenRAIL-M. FLUX.1-schnell and the Qwen LLMs are permissive
  (Apache-2.0). Each entry's licence note is in
  [`models.manifest.json`](models.manifest.json).

## Troubleshooting

- **`git` / `ollama` not found** — install them and reopen the terminal so PATH
  updates.
- **ReActor (face-swap) fails to build InsightFace** — install the prebuilt
  `cp311` wheel from `github.com/Gourieff/Assets`, then re-run the installer.
- **numpy got upgraded** by another node and broke ReActor/LivePortrait —
  re-run `python setup/install.py --steps nodes` (it re-pins `numpy==1.26.4`).
- **A model 404s** — the source repo/quant may have moved; update its entry in
  `models.manifest.json` (the RTX playbook lists the right orgs).
