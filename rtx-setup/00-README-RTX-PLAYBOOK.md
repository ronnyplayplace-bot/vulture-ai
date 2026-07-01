# 🚀 OVRLKD Studio — RTX-3060-Umbau-Playbook

> Ziel: Am Tag des GPU-Einbaus alles in geordneten Wellen aktivieren. Reihenfolge einhalten!
> **Prinzip (Ronnys Regel): vor jedem Download kurz prüfen ob's eine NEUERE/bessere Version gibt.** Modell-Repos driften — die hier genannten Orgs (QuantStack, city96, lightx2v, Kijai, Lightricks) sind die richtigen Anlaufstellen, aber check die neueste Quant/Version.

---

## ⚠️ HARDWARE-WAHRHEIT (damit keine falschen Erwartungen)
- RTX 3060 = **Ampere sm_86**: hat Tensor-Cores ✓, aber **KEINE fp8/fp4-Beschleunigung**. fp8 spart nur VRAM, macht NICHT schneller. Blackwell-Tricks (NVFP4, SageAttn3, Nunchaku-**Video**) laufen GAR NICHT.
- **Wir bleiben auf cu121 / torch 2.5.1** — die 3060 läuft damit perfekt, KEINE Stack-Migration (anders als Blackwell/5090, die cu128 bräuchten).
- **RAM ist der zweite Flaschenhals: 32GB sind PFLICHT für Video** (Encoder-Offload frisst ~9-10GB RAM). + Auslagerungsdatei 64-128GB (darf auf D:). → **die 32GB DDR4 mitkaufen.**
- Video heißt **Minuten bis Stunden pro Clip, nie Echtzeit** — das ist normal.

---

## WELLE 0 — Hardware rein & verifizieren  →  `01-verify-gpu.cmd`
- [ ] 8-Pin-Stromstecker dran (3060 braucht extra Strom, 1060 evtl. nicht)
- [ ] Alte Treiber sauber raus (DDU im abgesicherten Modus), **NVIDIA Studio-Treiber** neu
- [ ] `01-verify-gpu.cmd` ausführen → muss **compute cap 8.6** + 12GB zeigen
- [ ] Auslagerungsdatei auf D: vergrößern (System → Erweitert → Leistung → Virtueller Arbeitsspeicher → 64-128GB)
- [ ] `auto-tune-ctx.py` läuft beim nächsten KI-Coder-Start automatisch → num_ctx steigt von selbst (Pascal-Cap fällt weg, da cap≥7.0)

---

## WELLE 1 — Beschleunigung zuerst (multipliziert alles danach)  →  `04-acceleration.cmd`
- [ ] **ComfyUI mit `--fast` starten** (statt --lowvram; 12GB verträgt mehr)
- [ ] **triton-windows** (woct0rdho) für `torch.compile` (~10-30% überall) — läuft auf cu121
- [ ] **SageAttention 2** optional (~10-15% auf Ampere, NICHT die beworbenen 2× — Blackwell-only) + KJNodes-Patch gegen Wan-Black-Frame-Bug
- [ ] Studio-Starter `ensure_comfy()` von `--lowvram` auf `--fast` umstellen (studio.py Zeile ~48)

---

## WELLE 2 — VIDEO (das große Ziel)  →  `02-comfyui-video-nodes.cmd` + Modelle laden
**Nodes (clonen):** ComfyUI-LTXVideo (Lightricks), ComfyUI-GGUF (city96), ComfyUI-KJNodes (Kijai), ComfyUI-WanVideoWrapper (Kijai). *(VideoHelperSuite ist schon installiert ✓)*

**Modelle → immer nach D:\comfyui\ComfyUI\models\... :**
| Modell | Quelle (HF) | Wohin | Zweck |
|---|---|---|---|
| **LTX-2.3 distilled GGUF Q4_K_M** | Lightricks/LTX-2.3 + Community-GGUF | unet/ | **Daily-Driver, MIT Ton**, 8 Steps |
| LTX Audio-VAE + Gemma-Encoder (GGUF) | dito | vae/ + text_encoders/ | für LTX-Ton |
| **Wan 2.2 TI2V-5B GGUF Q6/Q8** | QuantStack od. city96 | unet/ + vae(wan2.2_vae) | chill 480p, kein Offload |
| **Wan 2.2 14B GGUF Q4_K_M** (beide Experten!) | QuantStack/Wan2.2-I2V-A14B-GGUF | unet/ | Qualität/Bewegung (langsam) |
| **Wan2.2-Lightning 4-Step LoRA** | lightx2v/Wan2.2-Lightning | loras/ | **~4× schneller (#1-Hebel!)** |
| (optional) Phr00t Rapid-AllInOne | Phr00t/WAN2.2-14B-Rapid-AllInOne | unet/ | bequeme 14B-Single-File |

- [ ] ⚠️ **LTX cu121-Pfad gegenchecken:** das offizielle pip-Paket will cu128/py3.12 — der **ComfyUI-native + GGUF-Pfad läuft auf cu121** (Community bestätigt). Am Tag kurz testen.
- [ ] Danach: Video-Kachel "🎬 Video" ins Studio bauen (LTX schnell + Wan Qualität, wie Bild-Generator)

---

## WELLE 3 — AUDIO / Stimme (komplette Lücke schließen)  →  `06-tts-audio.cmd`
- [ ] **TTS-Audio-Suite** (diodiogod) clonen — bündelt Chatterbox (Voice-Clone, winzig) + VibeVoice (7B, Multi-Speaker)
- [ ] Modelle laden (Chatterbox ~0,5B, VibeVoice ~7B) → D:
- [ ] Kachel "🔊 Stimme" ins Studio (Text→Sprache, deine Stimme klonen aus .wav)

---

## WELLE 4 — MUSIK für Gameplays  →  `07-music-acestep.cmd`
- [ ] **ACE-Step 1.5** (Text→Musik, <4GB VRAM, royaltyfrei) — ComfyUI-Node od. standalone
- [ ] Kachel "🎵 Musik" ins Studio (Prompt → Instrumental/Song)

---

## WELLE 5 — Bild-Upgrades + INT4-Turbo
- [ ] **Nunchaku** (`05-nunchaku.cmd`): ComfyUI-nunchaku + Wheel **passend zu torch 2.5.1+cu121+py-Version**. INT4 für FLUX/Qwen-Image (~3× schneller). ⚠️ NICHT für Video (nur Bild).
- [ ] **Qwen-Image / Qwen-Image-Edit 2511** (GGUF) — bestes Text-in-Bild + Editing. Mit Nunchaku auf 12GB nutzbar.
- [ ] **Z-Image Turbo** (6B, few-step, Photorealismus) — neuer Schnell-Default
- [ ] **Chroma** (unzensiertes FLUX, Apache) — freie LoRA-Basis
- [ ] **LanPaint** — sauberes Inpainting für jedes Modell

---

## WELLE 6 — Eigene LoRAs trainieren  →  `08-lora-onetrainer.cmd`
- [ ] **OneTrainer** (Nerogar) clonen, eigenes venv, cu121-torch
- [ ] **Erstes Projekt: Ronny-Gesicht-LoRA** (15-25 Fotos von dir) → FLUX/SDXL malt dich nativ in jeder Pose (Profi-Face-Swap)
- [ ] Dann: Game-Charakter-LoRA (Konsistenz), OVRLKD-Signature-Stil
- [ ] SDXL-LoRA easy auf 12GB; FLUX-LoRA eng → ggf. Cloud-5090

---

## WELLE 7 — Coding besser  →  `03-coding-models.cmd`
- [ ] **Qwen2.5-Coder-14B Q4_K_M** als neuer Default (passt komplett auf 12GB, ~30 tok/s) — **Unsloth-GGUF** (besseres Tool-Calling!)
- [ ] Optional **Qwen3-Coder-30B-A3B** (MoE, Offload→RAM, ~12 tok/s) für harte Tasks
- [ ] Auto-Test-Loop ist schon aktiv ✓; Architect/Editor-2-Modell-Setup testen
- [ ] (Schon erledigt: setup-project-coding.py, Flash-Attn, Q8-KV-Cache)

---

## WELLE 8 — Talking-Avatare (Bonus, besser als LivePortrait für Audio)
- [ ] **LatentSync 1.5** (~6,5GB) — Lippen auf bestehendes Video synchronisieren (Dub)
- [ ] **Wan-S2V / InfiniteTalk** (GGUF Q4 ~3GB) — Standbild + Audio → sprechendes Video
- [ ] (LivePortrait bleibt für Mimik/Bewegung — läuft schon ✓)

---

## ☁️ CLOUD-OPTION (separat, wenn's mal richtig krachen soll)
- 5090 mieten (vast.ai/runpod ~0,5-1€/h) für: 720p/1080p-Video, FLUX/SDXL-LoRA in Minuten, 32B-Coder.
- Braucht cu128-Image (Blackwell) — GGUF via aktuelles llama.cpp/Ollama „just works".
- **PRIVACY:** persönliche Daten (Chats, eigene Fotos) nur auf ephemeren Instanzen + vorher bereinigt. Fertiges Modell dann lokal nutzen.

---

## ✅ Test-Checkliste nach allen Wellen
- [ ] 1 FLUX-Bild (sollte ~5-10× schneller sein als auf 1060)
- [ ] 1 LTX-Video-Clip mit Ton
- [ ] 1 Wan-14B-Clip (Qualität)
- [ ] 1 Stimm-Klon (TTS)
- [ ] 1 Musik-Clip (ACE-Step)
- [ ] 1 Face-Swap + 1 Lip-Sync (sollten viel schneller sein)
- [ ] Coding mit 14B + Auto-Test-Loop
- [ ] Speicher-frei + Alles-stoppen funktionieren noch

Siehe auch: [[ovrlkd-roadmap]] (Memory) für Begründungen & Quellen.
