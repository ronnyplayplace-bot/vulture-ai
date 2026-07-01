<p align="center">
  <img src="docs/logo.png" alt="Vulture AI" width="200">
</p>

# Vulture AI

### by Overlkd Studio

**A fully offline, private AI creative studio in one clean desktop app.**
No cloud, no API keys, no subscriptions — nothing leaves your machine.

*Named after the vulture: it soars high above and sees everything — yet stays entirely on your machine.*

> ⚠️ **Early / work-in-progress.** It currently runs on the author's setup and
> hasn't been widely tested on other machines yet. Cross-machine setup is the
> first thing being worked on — contributions welcome!

---

![Overlkd Studio — one clean window, every tool in one place, no node spaghetti](docs/screenshot.png)

## What it is

Every individual AI tool out there is brilliant — but you spend more time gluing
them together than actually using them. Overlkd Studio wraps them into **one
window** so non-technical people can use them too. No ComfyUI node spaghetti,
no terminal.

## Features (all local / offline)

- 🎨 **Image generation** — FLUX (GGUF) + several SD1.5 models, with a built-in
  **prompt optimizer** (a local LLM turns your casual text into a proper prompt)
- 🔍 **4K upscaling** — 4x-UltraSharp + tiled Ultimate SD Upscale (real detail)
- 🖼️ **img2img** reworking
- 🎭 **Face-swap** (ReActor) and 👄 **lip-sync / talking photos** (LivePortrait)
- 💬 **Local chat** — Ollama (Qwen, DeepSeek-R1, vision models) + Open WebUI
- 💻 **Local coding agent** — Aider + local models, with an auto test→repair loop
  and an **auto-splitter** that breaks a big prompt into small steps so weaker
  local models don't choke
- 🧠 **Two local RAGs, one embedded store** — **Code-RAG** searches **your own**
  projects by meaning (pick a folder or clone a public GitHub repo), and
  **Chat-RAG** keeps chat memory across sessions. Both live in the same embedded
  local RAG (Qdrant + local embeddings), reachable from the **Code search**
  window — 100% local, nothing on any server, nothing leaves your machine.
  (Auto-filling chat memory from the chat UI is an optional integration.)
- ⚙️ Context size **auto-scales** to your GPU — zero manual tuning

## A look inside

<table>
  <tr>
    <td width="50%"><img src="docs/gallery/create-images.png" width="400"><br><b>Create images</b> — FLUX + prompt optimizer, HD / 4K upscale, img2img</td>
    <td width="50%"><img src="docs/gallery/face-swap.png" width="400"><br><b>Face swap</b> — your face onto any target, fully offline</td>
  </tr>
  <tr>
    <td><img src="docs/gallery/lip-sync.png" width="400"><br><b>Lip sync</b> — a photo brought to life by a driving video</td>
    <td><img src="docs/gallery/setup.png" width="400"><br><b>Setup &amp; install</b> — hardware check, per-GPU speed estimates, one-click install</td>
  </tr>
</table>

## Get started

**Prerequisites — install these yourself first:** Windows · an NVIDIA GPU (6 GB+ VRAM) ·
[Python 3.11](https://www.python.org/downloads/) (tick *Add python.exe to PATH*) ·
[Git](https://git-scm.com/download/win) · the [Ollama app](https://ollama.com/download)
(runs the local chat & coding models) · ~100 GB free disk.

**The easy way — no terminal:**
1. Download this repo (green **Code** button → *Download ZIP*) and unzip it.
2. Double-click **`INSTALL.cmd`** — it downloads ComfyUI + the models and opens the app.
3. In the app, open **⚙ Setup** → pick your drive → **Install everything**.

**Prefer the terminal:**
```bat
git clone https://github.com/ronnyplayplace-bot/vulture-ai.git
cd vulture-ai
python setup/install.py
python studio.py
```

> ⚠️ **If your C: drive is full:** set the install location to another drive first —
> open **⚙ Setup → 📁 Choose folder** before installing (the plain `INSTALL.cmd` defaults
> to `%LOCALAPPDATA%` on C:).

**Non-commercial models** (face-swap / InsightFace, CodeFormer, the 4x-UltraSharp upscaler,
LivePortrait) are personal / research use only — **Vulture never downloads those.** The
**⚙ Setup → Manual models** section links you to each source and checks once you've placed
the file. Everything else installs by default and is fine for commercial use — see
[NOTICE](NOTICE).

## Runs on modest hardware

Most of this runs on a **GTX 1060 6GB**. It's slow on old cards, but it *works*.
More VRAM = much faster. A wave of RTX-era additions (local video, text-to-music,
voice cloning, LoRA training) is planned for a future release.

## Models are NOT included

This repo is just the **launcher, UI and setup scripts**. The AI models
(tens of GB, and some under non-commercial licenses) are **downloaded on your
machine** from their original sources during setup.

## Requirements (rough)

- Windows, Python 3.11, an NVIDIA GPU (6GB+; 12GB recommended)
- Ollama installed; ComfyUI (the studio can start it)
- ~100GB free disk for models (put them on a big drive!)

## Status & roadmap

- ✅ Working: image gen + optimizer, 4K upscale, img2img, face-swap,
  lip-sync, local chat, coding agent + auto-splitter, Code-RAG + Chat-RAG (both local)
- 🔜 Next: local **video** (LTX-2 / Wan 2.2), **text-to-music**, **voice cloning** (TTS),
  local **LoRA training**, cross-machine installer

> ⚙️ **Heads up:** the next wave (video, voice, LoRA training) needs more VRAM than a
> GTX 1060 — realistically a 12GB+ GPU. Development is currently bottlenecked by hardware.

## Support

Vulture AI is free and always will be. A ⭐ on GitHub helps a ton. 🙏

**Open to inquiries & collaboration** — feature ideas, integrations, or working
together on this: open an issue or reach out. And if you'd like to support the
work, grab our game **[By My Side](https://store.steampowered.com/app/4859700/By_My_Side/)**
on Steam. 🎮

## License

The **Vulture launcher/UI is [MIT](LICENSE)** — use, modify and share freely,
including commercially. Please keep the credit.

Vulture bundles nothing — it downloads and launches third-party tools and
models, each under its own license. **Most is commercial-friendly**: the default
**FLUX.1-schnell** (Apache-2.0), SD1.5, the Qwen/DeepSeek LLMs, Ollama,
Aider and ComfyUI. **A few models are non-commercial / research-only** —
face-swap (InsightFace), CodeFormer, the 4x-UltraSharp upscaler, FLUX.1-dev and
LivePortrait. These are **never auto-downloaded** — you fetch them yourself from
the Setup window's Manual models section. Full breakdown in [NOTICE](NOTICE).

## Credits

Built on the shoulders of ComfyUI, Ollama, Open WebUI, Aider, FLUX, Stable
Diffusion, ReActor, LivePortrait, Qdrant and many more.
Full list in [NOTICE](NOTICE). 🙏
