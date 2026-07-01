# -*- coding: utf-8 -*-
"""Overlkd Studio AI - One window for everything, incl. a simple image generator."""
import tkinter as tk
from tkinter import font as tkfont, ttk, messagebox, filedialog
import subprocess, socket, os, threading, webbrowser, json, urllib.request, time, random, io, shutil

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find the vulture pkg
from vulture.config import get_config
from vulture.hardware import detect_gpu, detect_ram_gb, speed_multiplier
cfg = get_config()

# --- was hard-coded, now from config.json / auto-detect ---
COMFY_PY   = cfg.comfy_python          # was r"D:\comfyui\venv\Scripts\python.exe"
COMFY_API  = cfg.comfy_api             # was "http://127.0.0.1:8188"
OUTPUT_DIR = cfg.output_dir            # was r"D:\comfyui\output"
TOOLS      = cfg.tools_dir             # was r"C:\Users\User\ai-memory-tools"

# ---- Overlkd editorial dark-purple palette ----
BG="#0a0a0a"; CARD="#1a1d27"; PANEL="#14141c"; DIV="#1c1c1c"
ACCENT="#9b5dff"; ACCENT_LT="#c084fc"; ACCENT_DK="#5a3aef"
FG="#f0f0f0"; SUB="#888888"; GREEN="#3ddc84"; RED="#ff4d4d"

SLOGANS = ["We build things others overlook.",
           "It sees everything - nothing leaves your machine.",
           "Local . Private . Yours."]
SUPPORT = [("BTC", "37W7Djk14P9kw3Gx3zWLNXpTyRcSJfrwSe"),
           ("ETH", "0x30d7d100fe6606a0860786dacb975c7f7723852c"),
           ("USDT (BEP20)", "0x30d7d100fe6606a0860786dacb975c7f7723852c")]
SUPPORT_URL = "https://github.com/ronnyplayplace-bot/vulture-ai"
GAME_NAME = "By My Side"
GAME_URL = "https://store.steampowered.com/app/4859700/By_My_Side/"

SERVICES = cfg.services

NEG = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, worst quality, low quality, jpeg artifacts, signature, watermark, blurry, ugly, deformed, mutated"

# Model -> (engine, file)  -- FLUX is the default (best quality)
MODELS = {
    "FLUX  (best quality)":            ("flux", cfg.model_flux_unet),
    "DreamShaper  (fast/draft)":       ("sd15", "DreamShaper_v8.safetensors"),
    "Realistic Vision  (photo, fast)": ("sd15","RealisticVision_v6.safetensors"),
    "ToonYou  (cartoon, fast)":        ("sd15", "ToonYou_v6.safetensors"),
}
# (base resolution, hi-res factor) -> final result is base * factor
SIZES = {
    "Square HD (1024x1024)":    (512,512,2.0),
    "Portrait HD (1024x1536)":  (512,768,2.0),
    "Landscape HD (1536x1024)": (768,512,2.0),
    "Square fast (512)":        (512,512,1.0),
}

def port_open(p):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(0.3)
    try: return s.connect_ex((cfg.host,p))==0
    finally: s.close()

def run_hidden(cmd): subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
def run_visible(cmd): subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

def ensure_comfy():
    if not port_open(cfg.comfy_port):
        run_hidden(cfg.comfy_start_command())
        return False
    return True

def free_memory():
    # Restarting ComfyUI actually frees the RAM (Torch gives nothing back otherwise)
    try: urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/free",data=b'{"unload_models":true,"free_memory":true}',headers={"Content-Type":"application/json"}),timeout=5)
    except: pass
    run_hidden(f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {cfg.comfy_port} -State Listen -EA SilentlyContinue | %% {{ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }}"')

def start_all(): run_hidden(f'"{cfg.start_all_cmd}" silent')
def stop_all():
    run_hidden('taskkill /F /IM open-webui.exe /T')
    run_hidden(f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {cfg.comfy_port},{cfg.webui_port},{cfg.rag_port} -State Listen -EA SilentlyContinue | %% {{ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }}"')

def start_webui_and_open():
    # Open WebUI launcher lives in the repo's rag/ (written by setup/install.py
    # step_webui). Not the old cross-project cfg.tools_dir path.
    launcher=os.path.join(os.path.dirname(os.path.abspath(__file__)),"rag","start-webui.cmd")
    if not port_open(cfg.webui_port) and os.path.exists(launcher):
        run_hidden(f'"{launcher}"')
    webbrowser.open(cfg.webui_url)
def _open_cmd(path):
    # reliably open a console window (os.startfile launches the .cmd in its own window)
    try: os.startfile(path)
    except Exception:
        subprocess.Popen(f'start "Overlkd" "{path}"', shell=True)
def open_coder(): _open_cmd(cfg.coder_cmd)
def open_status(): _open_cmd(cfg.status_cmd)

# ---------- Code-RAG (local, private semantic code search) ----------
RAG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag")
def start_rag_service(visible=False):
    """Start the local Code-RAG server (rag/start-rag.cmd) if it isn't already
    listening. Hidden by default (no console window); pass visible=True to open a
    console for debugging (e.g. to watch the first-run model download / errors).
    100% local (127.0.0.1)."""
    if port_open(cfg.rag_port): return True
    cmd = os.path.join(RAG_DIR, "start-rag.cmd")
    if os.path.exists(cmd):
        if visible: _open_cmd(cmd)
        else: run_hidden(f'"{cmd}"')
    return False

def stop_service_port(port):
    """Stop whatever local service is listening on ``port`` (kill its process)."""
    run_hidden('powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort '
               f'{port} -State Listen -EA SilentlyContinue | %% {{ Stop-Process '
               '-Id $_.OwningProcess -Force -EA SilentlyContinue }}"')

def studio_update():
    """One-click update: ``git pull`` in the Studio folder. Only works when Vulture
    AI was installed via ``git clone`` (then this folder is the git repo)."""
    here = os.path.dirname(os.path.abspath(__file__))
    def show(kind, msg): root.after(0, lambda: getattr(messagebox, kind)("Update", msg))
    if not os.path.isdir(os.path.join(here, ".git")):
        show("showinfo", "This install isn't a git clone, so there's nothing to pull.\n\n"
             "For one-click updates, install Vulture AI with:\n"
             "    git clone <repo-url>\nand run studio.py from that folder.")
        return
    def worker():
        try:
            r = subprocess.run(["git", "pull", "--ff-only"], cwd=here, capture_output=True,
                               text=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
            out = ((r.stdout or "") + (r.stderr or "")).strip()
            if r.returncode != 0:
                show("showwarning", "Update failed:\n\n" + out[-600:]); return
            if "up to date" in out.lower():
                show("showinfo", "Already on the latest version. ✅")
            else:
                show("showinfo", "Updated! ✅\n\n" + out[-500:] + "\n\nRestart the Studio to apply.")
        except FileNotFoundError:
            show("showwarning", "git is not installed — install Git to enable updates.")
        except Exception as e:
            show("showwarning", f"Update error: {e}")
    threading.Thread(target=worker, daemon=True).start()

# ---------- Workflows ----------
def wf_sd15(model, prompt, w, h, seed, hires=2.0):
    wf = {
      "3":{"inputs":{"seed":seed,"steps":28,"cfg":7,"sampler_name":"dpmpp_2m","scheduler":"karras","denoise":1,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["5",0]},"class_type":"KSampler"},
      "4":{"inputs":{"ckpt_name":model},"class_type":"CheckpointLoaderSimple"},
      "5":{"inputs":{"width":w,"height":h,"batch_size":1},"class_type":"EmptyLatentImage"},
      "6":{"inputs":{"text":prompt,"clip":["4",1]},"class_type":"CLIPTextEncode"},
      "7":{"inputs":{"text":NEG,"clip":["4",1]},"class_type":"CLIPTextEncode"},
      "8":{"inputs":{"samples":["3",0],"vae":["4",2]},"class_type":"VAEDecode"},
      "9":{"inputs":{"filename_prefix":"studio","images":["8",0]},"class_type":"SaveImage"},
    }
    if hires and hires>1.0:
        # Hi-res fix: 2x latent upscale + second sampler pass (real detail)
        wf["10"]={"inputs":{"samples":["3",0],"scale_by":hires},"class_type":"LatentUpscaleBy"}
        wf["11"]={"inputs":{"seed":seed,"steps":16,"cfg":7,"sampler_name":"dpmpp_2m","scheduler":"karras","denoise":0.45,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["10",0]},"class_type":"KSampler"}
        wf["8"]["inputs"]["samples"]=["11",0]
    return wf
def wf_flux(prompt, w, h, seed):
    # Pascal optimisation: use the t5 Q8 GGUF if present (better than fp8), else fp8 fallback
    t5gguf=cfg.flux_t5_gguf_path()
    if os.path.exists(t5gguf) and os.path.getsize(t5gguf)>1000000:
        clip_node={"inputs":{"clip_name1":cfg.model_flux_t5_gguf,"clip_name2":cfg.model_flux_clip_l,"type":"flux"},"class_type":"DualCLIPLoaderGGUF"}
    else:
        clip_node={"inputs":{"clip_name1":cfg.model_flux_t5_fp8,"clip_name2":cfg.model_flux_clip_l,"type":"flux"},"class_type":"DualCLIPLoader"}
    return {
      "6":{"inputs":{"text":prompt,"clip":["11",0]},"class_type":"CLIPTextEncode"},
      "5":{"inputs":{"width":w,"height":h,"batch_size":1},"class_type":"EmptySD3LatentImage"},
      "11":clip_node,
      "10":{"inputs":{"vae_name":cfg.model_flux_vae},"class_type":"VAELoader"},
      "12":{"inputs":{"unet_name":cfg.model_flux_unet},"class_type":"UnetLoaderGGUF"},
      "13":{"inputs":{"noise":["25",0],"guider":["22",0],"sampler":["16",0],"sigmas":["17",0],"latent_image":["5",0]},"class_type":"SamplerCustomAdvanced"},
      "22":{"inputs":{"model":["12",0],"conditioning":["6",0]},"class_type":"BasicGuider"},
      "16":{"inputs":{"sampler_name":"euler"},"class_type":"KSamplerSelect"},
      "17":{"inputs":{"scheduler":"simple","steps":4,"denoise":1.0,"model":["12",0]},"class_type":"BasicScheduler"},
      "25":{"inputs":{"noise_seed":seed},"class_type":"RandomNoise"},
      "8":{"inputs":{"samples":["13",0],"vae":["10",0]},"class_type":"VAEDecode"},
      "9":{"inputs":{"filename_prefix":"studio_flux","images":["8",0]},"class_type":"SaveImage"},
    }

def wf_img2img(infile, prompt, ckpt, denoise, seed):
    # Image -> image (variation/reshape) - native SD1.5 nodes, runs on 6GB
    return {
      "1":{"inputs":{"image":infile,"upload":"image"},"class_type":"LoadImage"},
      "4":{"inputs":{"ckpt_name":ckpt},"class_type":"CheckpointLoaderSimple"},
      "5":{"inputs":{"pixels":["1",0],"vae":["4",2]},"class_type":"VAEEncode"},
      "6":{"inputs":{"text":prompt,"clip":["4",1]},"class_type":"CLIPTextEncode"},
      "7":{"inputs":{"text":NEG,"clip":["4",1]},"class_type":"CLIPTextEncode"},
      "3":{"inputs":{"seed":seed,"steps":28,"cfg":7,"sampler_name":"dpmpp_2m","scheduler":"karras",
            "denoise":denoise,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["5",0]},"class_type":"KSampler"},
      "8":{"inputs":{"samples":["3",0],"vae":["4",2]},"class_type":"VAEDecode"},
      "9":{"inputs":{"filename_prefix":"img2img","images":["8",0]},"class_type":"SaveImage"},
    }

def run_img2img(src_path, prompt, denoise, on_status, on_image):
    import shutil
    try:
        if not src_path or not os.path.exists(src_path): on_status("No source image."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(cfg.comfy_port): break
            time.sleep(2)
        inp=cfg.comfy_input_dir; os.makedirs(inp,exist_ok=True)
        fn="to_img2img.png"; shutil.copy(src_path, os.path.join(inp,fn))
        seed=random.randint(0,2**31)
        wf=wf_img2img(fn, prompt or "high quality, detailed", "RealisticVision_v6.safetensors", denoise, seed)
        path=comfy_run(wf, on_status, "Image→Image")
        if path: on_status("Image→Image done!"); on_image(path)
        else: on_status("Image→Image failed.")
    except Exception as e:
        on_status(f"Image→Image error: {e}")

def wf_upscale(infile, scale, ckpt, seed):
    # 4x-UltraSharp + Ultimate SD Upscale (SD1.5 refine, tiled) -> real 4K detail on 6GB
    return {
      "1":{"inputs":{"image":infile,"upload":"image"},"class_type":"LoadImage"},
      "2":{"inputs":{"ckpt_name":ckpt},"class_type":"CheckpointLoaderSimple"},
      "3":{"inputs":{"text":"high quality, sharp focus, highly detailed, intricate detail, 8k","clip":["2",1]},"class_type":"CLIPTextEncode"},
      "4":{"inputs":{"text":"blurry, low quality, jpeg artifacts, oversharpened, deformed","clip":["2",1]},"class_type":"CLIPTextEncode"},
      "5":{"inputs":{"model_name":cfg.model_upscale},"class_type":"UpscaleModelLoader"},
      "6":{"inputs":{"image":["1",0],"model":["2",0],"positive":["3",0],"negative":["4",0],"vae":["2",2],
            "upscale_model":["5",0],"upscale_by":scale,"seed":seed,"steps":20,"cfg":6.0,
            "sampler_name":"dpmpp_2m","scheduler":"karras","denoise":0.3,
            "mode_type":"Chess","tile_width":512,"tile_height":512,"mask_blur":8,"tile_padding":32,
            "seam_fix_mode":"Half Tile + Intersections","seam_fix_denoise":0.35,"seam_fix_width":64,
            "seam_fix_mask_blur":8,"seam_fix_padding":16,"force_uniform_tiles":True,"tiled_decode":True,"batch_size":1},
          "class_type":"UltimateSDUpscale"},
      "9":{"inputs":{"filename_prefix":"upscaled","images":["6",0]},"class_type":"SaveImage"},
    }

def run_upscale(src_path, scale, on_status, on_image):
    import shutil
    try:
        if not src_path or not os.path.exists(src_path):
            on_status("No image to upscale."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(cfg.comfy_port): break
            time.sleep(2)
        # ComfyUI loads LoadImage from input/ -> copy the image there
        inp=cfg.comfy_input_dir; os.makedirs(inp,exist_ok=True)
        fn="to_upscale.png"; shutil.copy(src_path, os.path.join(inp,fn))
        seed=random.randint(0,2**31)
        wf=wf_upscale(fn, scale, "RealisticVision_v6.safetensors", seed)
        path=comfy_run(wf, on_status, f"Upscaling {int(scale)}x")
        if path: on_status("Upscale done!"); on_image(path)
        else: on_status("May still be running in ComfyUI - check the images folder (can take a while on 6GB).")
    except Exception as e:
        on_status(f"Upscale error: {e}")

def wf_faceswap(target_file, source_file, restore_model="codeformer.pth", visibility=1.0):
    # ReActor face swap: face from source_file -> onto target_file. Runs offline (inswapper_128 + buffalo_l).
    return {
      "1":{"inputs":{"image":target_file,"upload":"image"},"class_type":"LoadImage"},
      "2":{"inputs":{"image":source_file,"upload":"image"},"class_type":"LoadImage"},
      "3":{"inputs":{
            "enabled":True,"input_image":["1",0],"source_image":["2",0],
            "swap_model":cfg.model_swap,"facedetection":"retinaface_resnet50",
            "face_restore_model":restore_model,"face_restore_visibility":visibility,"codeformer_weight":0.5,
            "detect_gender_input":"no","detect_gender_source":"no",
            "input_faces_index":"0","source_faces_index":"0","console_log_level":1},
          "class_type":"ReActorFaceSwap"},
      "9":{"inputs":{"filename_prefix":"faceswap","images":["3",0]},"class_type":"SaveImage"},
    }

# Smoothing level -> (CodeFormer model, visibility)
SWAP_RESTORE = {"none":("none",0.0), "light":(cfg.model_restore,0.5), "strong":(cfg.model_restore,1.0)}

def run_faceswap(target_path, source_path, restore_key, on_status, on_image):
    import shutil
    try:
        if not source_path or not os.path.exists(source_path): on_status("No face image selected."); return
        if not target_path or not os.path.exists(target_path): on_status("No target image selected."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(cfg.comfy_port): break
            time.sleep(2)
        inp=cfg.comfy_input_dir; os.makedirs(inp,exist_ok=True)
        te=os.path.splitext(target_path)[1].lower() or ".png"; se=os.path.splitext(source_path)[1].lower() or ".png"
        tn="swap_target"+te; sn="swap_source"+se
        shutil.copy(target_path, os.path.join(inp,tn)); shutil.copy(source_path, os.path.join(inp,sn))
        model,vis=SWAP_RESTORE.get(restore_key,(cfg.model_restore,1.0))
        wf=wf_faceswap(tn, sn, model, vis)
        path=comfy_run(wf, on_status, "Face swap")
        if path: on_status("Face swapped!"); on_image(path)
        else: on_status("May still be running in ComfyUI - check the images folder.")
    except Exception as e:
        on_status(f"Face swap error: {e}")

def wf_lipsync(source_file, driving_file, expressiveness=1.0):
    # LivePortrait: expressions/lips from driving_file (video) -> onto source_file (photo). Audio is passed through.
    return {
      "1":{"inputs":{"precision":"auto","mode":"human"},"class_type":"DownloadAndLoadLivePortraitModels"},
      "2":{"inputs":{"onnx_device":"CUDA","keep_model_loaded":True,"detection_threshold":0.5},"class_type":"LivePortraitLoadCropper"},
      "3":{"inputs":{"image":source_file},"class_type":"LoadImage"},
      "4":{"inputs":{"video":driving_file,"force_rate":25,"custom_width":0,"custom_height":0,
                     "frame_load_cap":0,"skip_first_frames":0,"select_every_nth":1,"format":"AnimateDiff"},"class_type":"VHS_LoadVideo"},
      "5":{"inputs":{"pipeline":["1",0],"cropper":["2",0],"source_image":["3",0],"dsize":512,"scale":2.3,
                     "vx_ratio":0.0,"vy_ratio":-0.125,"face_index":0,"face_index_order":"large-small","rotate":True},"class_type":"LivePortraitCropper"},
      "6":{"inputs":{"pipeline":["1",0],"crop_info":["5",1],"source_image":["3",0],"driving_images":["4",0],
                     "lip_zero":False,"lip_zero_threshold":0.03,"stitching":True,"delta_multiplier":expressiveness,
                     "mismatch_method":"constant","relative_motion_mode":"relative","driving_smooth_observation_variance":3e-06},"class_type":"LivePortraitProcess"},
      "7":{"inputs":{"source_image":["3",0],"cropped_image":["6",0],"liveportrait_out":["6",1]},"class_type":"LivePortraitComposite"},
      "8":{"inputs":{"images":["7",0],"frame_rate":25,"loop_count":0,"filename_prefix":"lipsync",
                     "format":"video/h264-mp4","pingpong":False,"save_output":True,"audio":["4",2]},"class_type":"VHS_VideoCombine"},
    }

def comfy_run_video(wf, on_status, label="Lip sync"):
    # like comfy_run, but at the end fetches a video file (gifs/videos) from the history
    cid=str(random.randint(1,2**31))
    try:
        pid=json.loads(urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/prompt",
            data=json.dumps({"prompt":wf,"client_id":cid}).encode(),headers={"Content-Type":"application/json"}),timeout=30).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        on_status("Send error: "+e.read().decode()[:200]); return None
    on_status(f"{label} running... (slow on 1060)")
    t0=time.time()
    while time.time()-t0<1800:
        time.sleep(4)
        try:
            h=json.loads(urllib.request.urlopen(f"{COMFY_API}/history/{pid}",timeout=8).read())
        except: continue
        if pid not in h: continue
        st=h[pid].get("status",{})
        if st.get("status_str")=="error": on_status("Processing error (check log)."); return None
        if st.get("completed") or st.get("status_str")=="success":
            for n,o in h[pid].get("outputs",{}).items():
                for g in o.get("gifs",[])+o.get("videos",[]):
                    return os.path.join(OUTPUT_DIR, g.get("filename"))
            return None
    return None

def run_lipsync(source_path, driving_path, expressiveness, on_status, on_done):
    import shutil
    try:
        if not source_path or not os.path.exists(source_path): on_status("No photo selected."); return
        if not driving_path or not os.path.exists(driving_path): on_status("No driving video selected."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(cfg.comfy_port): break
            time.sleep(2)
        inp=cfg.comfy_input_dir; os.makedirs(inp,exist_ok=True)
        se=os.path.splitext(source_path)[1].lower() or ".png"
        sn="lp_src"+se; dn="lp_drive.mp4"
        shutil.copy(source_path, os.path.join(inp,sn)); shutil.copy(driving_path, os.path.join(inp,dn))
        wf=wf_lipsync(sn, dn, expressiveness)
        path=comfy_run_video(wf, on_status, "Lip sync")
        if path: on_status("Lip sync done!"); on_done(path)
        else: on_status("May still be running in ComfyUI - check the images folder.")
    except Exception as e:
        on_status(f"Lip sync error: {e}")

def enhance_prompt(user_text):
    # Local AI (qwen) turns casual/German text into a good English FLUX prompt
    sys=("You are an expert text-to-image prompt engineer for FLUX. Convert the user's request "
         "(any language, may be casual) into ONE concise vivid ENGLISH image description. "
         "Describe ONLY what should be visible: subject, setting, style, lighting, mood, details. "
         "No instructions like 'create/make', no aspect ratio, no quotes, no explanation, no thinking. "
         "Output ONLY the final prompt as a single line.")
    body=json.dumps({"model":cfg.enhance_model,"prompt":user_text,"system":sys,"stream":False,
                     "keep_alive":0,  # unload the model from VRAM immediately -> room for FLUX (6GB!)
                     "options":{"temperature":0.6,"num_predict":300}}).encode()
    req=urllib.request.Request(f"{cfg.ollama_api}/api/generate",data=body,headers={"Content-Type":"application/json"})
    out=json.loads(urllib.request.urlopen(req,timeout=150).read()).get("response","")
    import re as _re
    out=_re.sub(r"<think>.*?</think>","",out,flags=_re.DOTALL).strip().strip('"').strip()
    return out

def comfy_run(wf, on_status, label="Generating"):
    # Sends the workflow + shows LIVE percent via websocket, returns the image path
    import websocket as _ws
    cid=str(random.randint(1,2**31))
    pid=json.loads(urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/prompt",
        data=json.dumps({"prompt":wf,"client_id":cid}).encode(),headers={"Content-Type":"application/json"}),timeout=30).read())["prompt_id"]
    try:
        ws=_ws.WebSocket(); ws.connect(f"{cfg.comfy_ws}?clientId={cid}",timeout=10); ws.settimeout(5)
    except Exception:
        ws=None
    done=False; t0=time.time()
    while not done:
        if time.time()-t0>2400: break  # 40min limit (upscaling on 6GB with many tiles takes a while)
        if ws is None: time.sleep(2)
        else:
            try:
                msg=ws.recv()
                if isinstance(msg,str):
                    m=json.loads(msg); t=m.get("type"); d=m.get("data",{})
                    if t=="progress" and d.get("max"):
                        on_status(f"{label} {int(d['value']/d['max']*100)}%")
                    elif t=="executing" and d.get("node") is None and d.get("prompt_id")==pid:
                        done=True
            except Exception:
                pass
        # Fallback: check the history
        try:
            h=json.loads(urllib.request.urlopen(f"{COMFY_API}/history/{pid}",timeout=8).read())
            if pid in h and h[pid].get("outputs"): done=True
        except: pass
    try:
        if ws: ws.close()
    except: pass
    h=json.loads(urllib.request.urlopen(f"{COMFY_API}/history/{pid}",timeout=10).read())
    if pid in h:
        for nid,out in h[pid].get("outputs",{}).items():
            for img in out.get("images",[]):
                return os.path.join(OUTPUT_DIR,img["filename"])
    return None

def generate(engine, model_file, prompt, w, h, hires, on_status, on_image):
    try:
        on_status("Starting ComfyUI..." if not port_open(cfg.comfy_port) else "Sending to AI...")
        if not ensure_comfy():
            for _ in range(60):
                if port_open(cfg.comfy_port): break
                time.sleep(2)
            time.sleep(3)
        # FLUX files present?
        if engine=="flux":
            need=cfg.flux_required_files()
            if not all(os.path.exists(p) and os.path.getsize(p)>1000000 for p in need):
                on_status("FLUX still downloading - please try later."); return
        seed=random.randint(0,2**31)
        wf = wf_flux(prompt,w,h,seed) if engine=="flux" else wf_sd15(model_file,prompt,w,h,seed,hires)
        lbl="Generating FLUX" if engine=="flux" else "Generating"
        path=comfy_run(wf, on_status, lbl)
        if path: on_status("Done!"); on_image(path)
        else: on_status("Timeout - may still be running, check the images folder.")
    except Exception as e:
        on_status(f"Error: {e}")

# ---------------- GUI ----------------
root=tk.Tk(); root.title("Vulture AI"); root.configure(bg=BG)
# App icon (Vulture AI logo) for the title bar / Alt-Tab / taskbar.
_APPDIR=os.path.dirname(os.path.abspath(__file__))
try:
    _ico=os.path.join(_APPDIR,"vulture.ico")
    if os.path.exists(_ico): root.iconbitmap(default=_ico)
except Exception: pass
try:
    _png=os.path.join(_APPDIR,"vulture.png")
    if os.path.exists(_png):
        _appicon=tk.PhotoImage(file=_png); root.iconphoto(True,_appicon)
except Exception: pass
root.geometry("900x600+140+80"); root.minsize(820,540); root.resizable(True,True)

# --- Dark-purple ttk.Combobox theming: field + readonly state + dropdown popup ---
_cbstyle=ttk.Style(); _cbstyle.theme_use("default")
_cbstyle.configure("TCombobox",fieldbackground=CARD,background=CARD,foreground=FG,
                   arrowcolor=ACCENT_LT,relief="flat",borderwidth=0,padding=6)
_cbstyle.map("TCombobox",
    fieldbackground=[("readonly",CARD),("disabled",PANEL)],
    foreground=[("readonly",FG),("disabled",SUB)],
    background=[("readonly",CARD)],
    selectbackground=[("readonly",CARD)],
    selectforeground=[("readonly",FG)],
    arrowcolor=[("readonly",ACCENT_LT)])
# The dropdown popup is a classic Tk Listbox that ignores ttk styling:
root.option_add("*TCombobox*Listbox.background",CARD)
root.option_add("*TCombobox*Listbox.foreground",FG)
root.option_add("*TCombobox*Listbox.selectBackground",ACCENT)
root.option_add("*TCombobox*Listbox.selectForeground","#0a0a0a")
root.option_add("*TCombobox*Listbox.borderWidth",0)
def _front():
    root.deiconify(); root.lift(); root.attributes("-topmost",True)
    root.after(800,lambda:root.attributes("-topmost",False)); root.focus_force()
root.after(100,_front)

title_f=tkfont.Font(family="Segoe UI",size=20,weight="bold")
btn_f=tkfont.Font(family="Segoe UI",size=13,weight="bold")
sub_f=tkfont.Font(family="Segoe UI",size=9); small_f=tkfont.Font(family="Segoe UI",size=9)
bar_f=tkfont.Font(family="Segoe UI",size=10,weight="bold")

# ---- Frameless custom chrome: our own flat title bar (no native window chrome) ----
def make_frameless(win, title, closer):
    win.configure(bg=BG)
    win.overrideredirect(True)
    try: win.attributes("-topmost", False)
    except: pass
    win.configure(highlightthickness=1, highlightbackground=ACCENT_DK, highlightcolor=ACCENT_DK)
    st={"maxed": False, "geo": None, "min": False}
    def do_min():
        # overrideredirect windows cannot be iconified directly -> briefly restore the frame, iconify, turn it off again on remap
        st["min"]=True
        win.overrideredirect(False); win.update_idletasks(); win.iconify()
    def _remap(e=None):
        try:
            if st["min"] and win.state()=="normal":
                win.overrideredirect(True); st["min"]=False
        except: pass
    win.bind("<Map>", _remap, add="+")
    def do_max():
        if st["maxed"]:
            if st["geo"]: win.geometry(st["geo"])
            st["maxed"]=False; mx.config(text="□")
        else:
            st["geo"]=win.geometry()
            win.geometry(f"{win.winfo_screenwidth()}x{win.winfo_screenheight()}+0+0")
            st["maxed"]=True; mx.config(text="❐")
    bar=tk.Frame(win,bg=PANEL,height=36); bar.pack(side="top",fill="x"); bar.pack_propagate(False)
    tlbl=tk.Label(bar,text=title,font=bar_f,bg=PANEL,fg=FG); tlbl.pack(side="left",padx=14)
    def _wb(sym,cmd,hovbg):
        b=tk.Label(bar,text=sym,font=("Segoe UI",12),bg=PANEL,fg=SUB,width=5,cursor="hand2")
        b.pack(side="right",fill="y")
        b.bind("<Button-1>",lambda e:cmd())
        b.bind("<Enter>",lambda e,bb=b:bb.config(bg=hovbg,fg="#ffffff"))
        b.bind("<Leave>",lambda e,bb=b:bb.config(bg=PANEL,fg=SUB))
        return b
    _wb("✕", closer, RED)
    mx=_wb("□", do_max, ACCENT)
    _wb("⚊", do_min, ACCENT)
    def _press(e): win._drag=(e.x_root, e.y_root, win.winfo_x(), win.winfo_y())
    def _move(e):
        if st["maxed"] or not hasattr(win,"_drag"): return
        x0,y0,wx,wy=win._drag
        win.geometry(f"+{wx+(e.x_root-x0)}+{wy+(e.y_root-y0)}")
    for wdg in (bar, tlbl):
        wdg.bind("<ButtonPress-1>", _press); wdg.bind("<B1-Motion>", _move)
    return bar

# ---- Subtle support dialog (copy crypto addresses) ----
def open_support_window():
    win=tk.Toplevel(root); win.title("Overlkd - Support"); win.geometry("440x470")
    win.lift(); win.focus_force()
    make_frameless(win, "♥  Support", win.destroy)
    tk.Label(win,text="Support keeps it free & offline.",font=sub_f,bg=BG,fg=ACCENT_LT).pack(pady=(16,4))
    # Best support: grab our game on Steam.
    gcard=tk.Frame(win,bg=CARD); gcard.pack(fill="x",padx=20,pady=(4,10))
    tk.Label(gcard,text="\U0001f3ae  Or buy our game",font=("Segoe UI",10,"bold"),
             bg=CARD,fg=ACCENT).pack(anchor="w",padx=10,pady=(8,0))
    tk.Label(gcard,text=f"{GAME_NAME} - survival co-op, on Steam",font=small_f,
             bg=CARD,fg=SUB).pack(anchor="w",padx=10)
    glink=tk.Label(gcard,text="→ View on Steam",font=("Segoe UI",9,"bold"),
                   bg=CARD,fg=ACCENT_LT,cursor="hand2")
    glink.pack(anchor="w",padx=10,pady=(2,8))
    glink.bind("<Button-1>",lambda e:webbrowser.open(GAME_URL))
    tk.Label(win,text="or copy an address to send a tip - thank you.",font=small_f,bg=BG,fg=SUB).pack(pady=(0,10))
    def copy(val,btn):
        win.clipboard_clear(); win.clipboard_append(val)
        btn.config(text="copied ✓")
        win.after(1200,lambda:btn.config(text="copy"))
    for label,addr in SUPPORT:
        card=tk.Frame(win,bg=CARD); card.pack(fill="x",padx=20,pady=4)
        tk.Label(card,text=label,font=("Segoe UI",9,"bold"),bg=CARD,fg=ACCENT_LT).pack(anchor="w",padx=10,pady=(8,0))
        rowf=tk.Frame(card,bg=CARD); rowf.pack(fill="x",padx=10,pady=(0,8))
        tk.Label(rowf,text=addr,font=("Consolas",8),bg=CARD,fg=FG,anchor="w").pack(side="left",fill="x",expand=True)
        cbtn=tk.Button(rowf,text="copy",font=small_f,bg=ACCENT,fg="#ffffff",relief="flat",cursor="hand2",
                       activebackground=ACCENT_DK,activeforeground="#ffffff")
        cbtn.config(command=lambda a=addr,b=cbtn:copy(a,b)); cbtn.pack(side="right",padx=(8,0))
    link=tk.Label(win,text=SUPPORT_URL,font=small_f,bg=BG,fg=SUB,cursor="hand2")
    link.pack(pady=(10,12)); link.bind("<Button-1>",lambda e:webbrowser.open(SUPPORT_URL))

make_frameless(root, "VULTURE AI", root.destroy)

# ---- Header ----
head=tk.Frame(root,bg=BG); head.pack(fill="x",padx=24,pady=(16,6))
tk.Label(head,text="VULTURE AI",font=title_f,bg=BG,fg=FG).pack(side="left")
_by=tk.Label(head,text="  by Overlkd Studio ↗",font=sub_f,bg=BG,fg=ACCENT_LT,cursor="hand2"); _by.pack(side="left",pady=(10,0))
_by.bind("<Button-1>",lambda e:webbrowser.open("https://www.overlkd.com"))
tk.Frame(root,bg=DIV,height=1).pack(fill="x",padx=24,pady=(0,2))

# ---- Footer: rotating slogan + subtle support link ----
foot=tk.Frame(root,bg=BG); foot.pack(side="bottom",fill="x",padx=24,pady=(0,8))
slogan_lbl=tk.Label(foot,text=SLOGANS[0],font=small_f,bg=BG,fg=SUB,width=52,anchor="w"); slogan_lbl.pack(side="left")
sup_lbl=tk.Label(foot,text="♥ Support",font=small_f,bg=BG,fg=ACCENT_LT,cursor="hand2"); sup_lbl.pack(side="right")
sup_lbl.bind("<Button-1>",lambda e:open_support_window())
setup_lbl=tk.Label(foot,text="⚙ Setup",font=small_f,bg=BG,fg=ACCENT_LT,cursor="hand2"); setup_lbl.pack(side="right",padx=(0,16))
setup_lbl.bind("<Button-1>",lambda e:open_setup_window())
req_lbl=tk.Label(foot,text="📋 Licenses",font=small_f,bg=BG,fg=ACCENT_LT,cursor="hand2"); req_lbl.pack(side="right",padx=(0,16))
req_lbl.bind("<Button-1>",lambda e:open_requirements_window())
def _rotate_slogan(i=0):
    slogan_lbl.config(text=SLOGANS[i % len(SLOGANS)])
    root.after(6000, lambda:_rotate_slogan(i+1))
root.after(6000,_rotate_slogan)

# ---- Body: actions on the left (grid), status on the right ----
body=tk.Frame(root,bg=BG); body.pack(fill="both",expand=True,padx=20,pady=(4,16))
left=tk.Frame(body,bg=BG); left.pack(side="left",fill="both",expand=True)
right=tk.Frame(body,bg=BG,width=210); right.pack(side="right",fill="y",padx=(16,0)); right.pack_propagate(False)

def _hover(fr,on,base):
    c="#26233a" if on else base
    fr.config(bg=c)
    for w in fr.winfo_children():
        w.config(bg=c)
        for w2 in w.winfo_children(): w2.config(bg=c)

def make_card(parent,r,c,emoji,text,sub,cmd,base=CARD,fg=FG,h=64):
    f=tk.Frame(parent,bg=base,cursor="hand2",height=h); f.grid(row=r,column=c,sticky="nsew",padx=5,pady=5)
    f.grid_propagate(False)
    inner=tk.Frame(f,bg=base); inner.place(relx=0.5,rely=0.5,anchor="center")
    tk.Label(inner,text=emoji+"  "+text,font=btn_f,bg=base,fg=fg).pack(anchor="w")
    if sub: tk.Label(inner,text=sub,font=small_f,bg=base,fg=SUB if base==CARD else fg).pack(anchor="w")
    for w in [f,inner]+list(inner.winfo_children()):
        w.bind("<Button-1>",lambda e,cc=cmd:cc())
        w.bind("<Enter>",lambda e,fr=f:_hover(fr,True,base))
        w.bind("<Leave>",lambda e,fr=f:_hover(fr,False,base))
    return f

for i in range(2): left.columnconfigure(i,weight=1)
for i in range(6): left.rowconfigure(i,weight=1)

# Start spans the full width
make_card(left,0,0,"▶","START ALL","Boot up services",start_all,base=ACCENT,fg="#ffffff").grid(columnspan=2,sticky="nsew")
make_card(left,1,0,"\U0001f3a8","Create images","Text in, image out",lambda:open_generator())
make_card(left,1,1,"\U0001f4ac","Chat","Local AI models",start_webui_and_open)
make_card(left,2,0,"\U0001f4bb","Coding agent","Aider (terminal)",open_coder)
make_card(left,2,1,"\U0001f4ca","Status","RAM / VRAM / GPU",open_status)
make_card(left,3,0,"\U0001f3ad","Face swap","Face swap (photo)",lambda:open_faceswap_window())
make_card(left,3,1,"\U0001f444","Lip sync","Bring a photo to life",lambda:open_lipsync_window())
make_card(left,4,0,"\U0001f50e","Code search","Index & search your own code — local",lambda:open_rag_window()).grid(columnspan=2,sticky="nsew")

# ---- Right column: service status + memory/stop ----
tk.Label(right,text="SERVICES",font=small_f,bg=BG,fg=SUB).pack(anchor="w",pady=(2,4))
status_labels={}
for name in SERVICES:
    row=tk.Frame(right,bg=BG); row.pack(fill="x",pady=1)
    dot=tk.Label(row,text="●",font=small_f,bg=BG,fg=RED); dot.pack(side="left")
    tk.Label(row,text=" "+name,font=small_f,bg=BG,fg=SUB,anchor="w").pack(side="left")
    status_labels[name]=dot

tk.Frame(right,bg=BG,height=12).pack()
free_f=tk.Frame(right,bg="#16241c",cursor="hand2"); free_f.pack(fill="x",pady=4)
tk.Label(free_f,text="\U0001f9f9  Free memory",font=sub_f,bg="#16241c",fg=GREEN).pack(pady=10)
for w in [free_f]+list(free_f.winfo_children()): w.bind("<Button-1>",lambda e:free_memory())
stop_f=tk.Frame(right,bg="#2a1518",cursor="hand2"); stop_f.pack(fill="x",pady=4)
tk.Label(stop_f,text="⏹  Stop all",font=sub_f,bg="#2a1518",fg=RED).pack(pady=10)
for w in [stop_f]+list(stop_f.winfo_children()): w.bind("<Button-1>",lambda e:stop_all())
upd_f=tk.Frame(right,bg="#161a24",cursor="hand2"); upd_f.pack(fill="x",pady=4)
tk.Label(upd_f,text="⟳  Update (GitHub)",font=small_f,bg="#161a24",fg=ACCENT_LT).pack(pady=8)
for w in [upd_f]+list(upd_f.winfo_children()): w.bind("<Button-1>",lambda e:studio_update())

def refresh():
    for name,port in SERVICES.items():
        status_labels[name].config(fg=GREEN if port_open(port) else RED)
    root.after(3000,refresh)
refresh()

# ---------- Image generator window ----------
def open_generator():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("Overlkd - Create images"); win.configure(bg=BG)
    win.geometry("760x860"); win.minsize(560,640); win.resizable(True,True)
    win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Create images", win.destroy)
    win._last_path=None; win._pil=None
    tk.Label(win,text="\U0001f3a8 Create images",font=title_f,bg=BG,fg=FG).pack(pady=(14,8))

    tk.Label(win,text="What should be in the image?",font=sub_f,bg=BG,fg=SUB).pack(anchor="w",padx=24)
    prompt_box=tk.Text(win,height=3,font=("Segoe UI",11),bg=CARD,fg=FG,insertbackground=FG,relief="flat",wrap="word")
    prompt_box.pack(fill="x",padx=24,pady=(2,10)); prompt_box.insert("1.0","")

    rowf=tk.Frame(win,bg=BG); rowf.pack(fill="x",padx=24)
    tk.Label(rowf,text="Model / Style",font=sub_f,bg=BG,fg=SUB).grid(row=0,column=0,sticky="w")
    tk.Label(rowf,text="Format",font=sub_f,bg=BG,fg=SUB).grid(row=0,column=1,sticky="w",padx=(12,0))
    model_var=tk.StringVar(value=list(MODELS.keys())[0])
    size_var=tk.StringVar(value=list(SIZES.keys())[0])
    style=ttk.Style(); style.theme_use("default")
    style.configure("TCombobox",fieldbackground=CARD,background=CARD,foreground=FG,arrowcolor=ACCENT_LT,relief="flat")
    mcb=ttk.Combobox(rowf,textvariable=model_var,values=list(MODELS.keys()),state="readonly",width=28); mcb.grid(row=1,column=0,sticky="w",pady=4)
    scb=ttk.Combobox(rowf,textvariable=size_var,values=list(SIZES.keys()),state="readonly",width=16); scb.grid(row=1,column=1,sticky="w",padx=(12,0),pady=4)

    enhance_var=tk.BooleanVar(value=True)
    tk.Checkbutton(win,text="✨ Optimize prompt with AI (casual text ok → produces an English FLUX prompt)",
        variable=enhance_var,font=sub_f,bg=BG,fg=FG,selectcolor=CARD,activebackground=BG,activeforeground=FG,anchor="w").pack(fill="x",padx=24,pady=(2,0))

    # Buttons FIRST (always visible, at the top), then the image fills the rest
    gen_btn=tk.Button(win,text="✨  Generate image",font=btn_f,bg=ACCENT,fg="#ffffff",relief="flat",cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff")
    gen_btn.pack(side="top",fill="x",padx=24,pady=(10,4))
    status_lbl=tk.Label(win,text="Ready.",font=sub_f,bg=BG,fg=GREEN); status_lbl.pack(side="top",pady=(2,4))

    # Bottom: open image large + folder
    botf=tk.Frame(win,bg=BG); botf.pack(side="bottom",fill="x",pady=(4,10))
    def open_full():
        if win._last_path and os.path.exists(win._last_path): os.startfile(win._last_path)
        else: os.startfile(OUTPUT_DIR)
    tk.Button(botf,text="\U0001f50d  Open image large",font=sub_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
              command=open_full).pack(side="left",expand=True,fill="x",padx=(24,6))
    tk.Button(botf,text="\U0001f4c1 Folder",font=sub_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",
              command=lambda:os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(6,24))
    # Image->image row (variation/reshape from a source image + prompt)
    i2f=tk.Frame(win,bg=BG); i2f.pack(side="bottom",fill="x",pady=(0,2))
    def do_img2img():
        f=filedialog.askopenfilename(title="Source image for Image→Image",initialdir=OUTPUT_DIR,
            filetypes=[("Images","*.png *.jpg *.jpeg *.webp"),("All","*.*")])
        if not f: return
        p=prompt_box.get("1.0","end").strip() or "high quality, detailed"
        set_status("Image→Image running...")
        threading.Thread(target=lambda:run_img2img(f,p,0.55,set_status,show_image),daemon=True).start()
    tk.Button(i2f,text="\U0001f5bc️ Image→Image (reshape source + prompt)",font=sub_f,bg="#1e1a2e",fg=ACCENT_LT,
              relief="flat",cursor="hand2",command=do_img2img).pack(fill="x",padx=24)
    # Upscale row (4x-UltraSharp + Ultimate SD Upscale -> real detail)
    upf=tk.Frame(win,bg=BG); upf.pack(side="bottom",fill="x",pady=(0,2))
    def do_upscale(scale):
        if not getattr(win,"_last_path",None): set_status("Generate or load an image first."); return
        threading.Thread(target=lambda:run_upscale(win._last_path,scale,set_status,show_image),daemon=True).start()
    def load_and_4k():
        from PIL import Image, ImageTk
        f=filedialog.askopenfilename(title="Load image to upscale",initialdir=OUTPUT_DIR,
            filetypes=[("Images","*.png *.jpg *.jpeg *.webp"),("All","*.*")])
        if not f: return
        win._last_path=f
        try:
            win._pil=Image.open(f); _rescale()
        except: pass
        set_status("Loaded - upscaling to 4K...")
        threading.Thread(target=lambda:run_upscale(f,4.0,set_status,show_image),daemon=True).start()
    tk.Button(upf,text="\U0001f53c HD (2x)",font=sub_f,bg=PANEL,fg=GREEN,relief="flat",cursor="hand2",
              command=lambda:do_upscale(2.0)).pack(side="left",expand=True,fill="x",padx=(24,3))
    tk.Button(upf,text="\U0001f53c 4K (4x)",font=sub_f,bg=PANEL,fg=GREEN,relief="flat",cursor="hand2",
              command=lambda:do_upscale(4.0)).pack(side="left",expand=True,fill="x",padx=3)
    tk.Button(upf,text="\U0001f4c2 Load image→4K",font=sub_f,bg=PANEL,fg=GREEN,relief="flat",cursor="hand2",
              command=load_and_4k).pack(side="left",expand=True,fill="x",padx=(3,24))

    img_lbl=tk.Label(win,bg=CARD,text="(your image appears here)",fg=SUB,font=sub_f)
    img_lbl.pack(side="top",padx=24,pady=6,fill="both",expand=True)
    img_lbl._ref=None

    def set_status(t): win.after(0,lambda:status_lbl.config(text=t))
    def _rescale():
        if not win._pil: return
        aw=max(img_lbl.winfo_width()-8,200); ah=max(img_lbl.winfo_height()-8,200)
        im=win._pil.copy(); im.thumbnail((aw,ah))
        ph=ImageTk.PhotoImage(im); img_lbl.config(image=ph,text=""); img_lbl._ref=ph
    def show_image(path):
        def _do():
            try:
                win._last_path=path; win._pil=Image.open(path); _rescale()
                set_status("Done! Saved as "+os.path.basename(path))
                os.startfile(path)  # opens automatically in the image viewer
            except Exception as e: set_status(f"Display error: {e}")
        win.after(0,_do)
    win.bind("<Configure>", lambda e: _rescale() if e.widget is win else None)

    def do_gen():
        p=prompt_box.get("1.0","end").strip()
        if not p: set_status("Please type something first."); return
        gen_btn.config(state="disabled",text="Generating...")
        engine,mf=MODELS[model_var.get()]; w,h,hires=SIZES[size_var.get()]
        def worker():
            pr=p
            if enhance_var.get():
                set_status("AI is optimizing your prompt...")
                try:
                    better=enhance_prompt(p)
                    if better: pr=better; set_status("Optimized: "+pr[:70]+"...")
                except Exception as e: set_status(f"Optimization skipped ({e}) - using original")
            generate(engine,mf,pr,w,h,hires,set_status,show_image)
            win.after(0,lambda:gen_btn.config(state="normal",text="✨  Generate image"))
        threading.Thread(target=worker,daemon=True).start()

    gen_btn.config(command=do_gen)

# ---------- Face swap window ----------
def open_faceswap_window():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("Overlkd - Face swap"); win.configure(bg=BG)
    win.geometry("640x760"); win.minsize(560,680); win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Face swap", win.destroy)
    win._src=None; win._tgt=None; win._last=None
    tk.Label(win,text="\U0001f3ad Face swap",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="Your face (1) goes onto the target image (2). Runs 100% offline.",font=small_f,bg=BG,fg=SUB).pack(pady=(0,8))

    grid=tk.Frame(win,bg=BG); grid.pack(fill="x",padx=24)
    grid.columnconfigure(0,weight=1); grid.columnconfigure(1,weight=1)
    srcvar=tk.StringVar(value="no face selected"); tgtvar=tk.StringVar(value="no target selected")
    tk.Label(grid,text="1) YOUR FACE",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=0,sticky="w")
    tk.Label(grid,text="2) TARGET IMAGE (body/scene)",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=1,sticky="w",padx=(6,0))
    src_prev=tk.Label(grid,bg=CARD,text="(Preview)",fg=SUB,font=small_f,height=9); src_prev.grid(row=1,column=0,sticky="nsew",padx=(0,6),pady=4); src_prev._ref=None
    tgt_prev=tk.Label(grid,bg=CARD,text="(Preview)",fg=SUB,font=small_f,height=9); tgt_prev.grid(row=1,column=1,sticky="nsew",padx=(6,0),pady=4); tgt_prev._ref=None
    def pick_into(which,prev,var):
        f=filedialog.askopenfilename(title="Choose image",initialdir=os.path.expanduser("~\\Desktop"),
            filetypes=[("Images","*.png *.jpg *.jpeg *.webp"),("All","*.*")])
        if not f: return
        if which=="src": win._src=f
        else: win._tgt=f
        var.set(os.path.basename(f)[:34])
        try:
            im=Image.open(f); im.thumbnail((250,250)); ph=ImageTk.PhotoImage(im)
            prev.config(image=ph,text=""); prev._ref=ph
        except: pass
    tk.Button(grid,text="\U0001f4c2 Choose face",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
        command=lambda:pick_into("src",src_prev,srcvar)).grid(row=2,column=0,sticky="ew",padx=(0,6),pady=2)
    tk.Button(grid,text="\U0001f4c2 Choose target",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
        command=lambda:pick_into("tgt",tgt_prev,tgtvar)).grid(row=2,column=1,sticky="ew",padx=(6,0),pady=2)
    tk.Label(grid,textvariable=srcvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=0,sticky="w")
    tk.Label(grid,textvariable=tgtvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=1,sticky="w",padx=(6,0))

    optf=tk.Frame(win,bg=BG); optf.pack(fill="x",padx=24,pady=(8,2))
    tk.Label(optf,text="Edge smoothing: ",font=sub_f,bg=BG,fg=SUB).pack(side="left")
    REST={"Strong (recommended)":"strong","Light":"light","Off (raw)":"none"}
    rest_var=tk.StringVar(value="Strong (recommended)")
    ttk.Combobox(optf,textvariable=rest_var,values=list(REST.keys()),state="readonly",width=18).pack(side="left")

    go=tk.Button(win,text="\U0001f3ad  Swap faces",font=btn_f,bg=ACCENT,fg="#ffffff",relief="flat",cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff")
    go.pack(fill="x",padx=24,pady=(10,4))
    st=tk.Label(win,text="Ready. First run loads models (~1-3 min on 6GB).",font=sub_f,bg=BG,fg=GREEN); st.pack(pady=(2,4))
    botf=tk.Frame(win,bg=BG); botf.pack(side="bottom",fill="x",pady=(4,10))
    tk.Button(botf,text="\U0001f50d Open large",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
        command=lambda:os.startfile(win._last) if win._last and os.path.exists(win._last) else os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(24,6))
    tk.Button(botf,text="\U0001f4c1 Folder",font=small_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",
        command=lambda:os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(6,24))
    res=tk.Label(win,bg=CARD,text="(result appears here)",fg=SUB,font=sub_f); res.pack(side="top",padx=24,pady=6,fill="both",expand=True); res._ref=None

    def set_st(t): win.after(0,lambda:st.config(text=t))
    def show(path):
        def _do():
            try:
                win._last=path; im=Image.open(path); im.thumbnail((400,400)); ph=ImageTk.PhotoImage(im)
                res.config(image=ph,text=""); res._ref=ph
                set_st("Done! "+os.path.basename(path)); os.startfile(path)
            except Exception as e: set_st(f"Display error: {e}")
        win.after(0,_do)
    def do_swap():
        if not win._src: set_st("Please select your face image first (1)."); return
        if not win._tgt: set_st("Please select a target image first (2)."); return
        go.config(state="disabled",text="Swapping...")
        key=REST.get(rest_var.get(),"strong")
        def worker():
            run_faceswap(win._tgt,win._src,key,set_st,show)
            win.after(0,lambda:go.config(state="normal",text="\U0001f3ad  Swap faces"))
        threading.Thread(target=worker,daemon=True).start()
    go.config(command=do_swap)

# ---------- Lip sync (LivePortrait) window ----------
def open_lipsync_window():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("Overlkd - Lip sync"); win.configure(bg=BG)
    win.geometry("640x620"); win.minsize(560,560); win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Lip sync", win.destroy)
    win._src=None; win._drv=None; win._last=None
    tk.Label(win,text="\U0001f444 Lip sync",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="Photo (1) is brought to life by a driving video (2) - expressions, lips, head. Audio is carried over.",
             font=small_f,bg=BG,fg=SUB,wraplength=600).pack(pady=(0,8))

    grid=tk.Frame(win,bg=BG); grid.pack(fill="x",padx=24)
    grid.columnconfigure(0,weight=1); grid.columnconfigure(1,weight=1)
    srcvar=tk.StringVar(value="no photo"); drvvar=tk.StringVar(value="no video")
    tk.Label(grid,text="1) PHOTO (face)",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=0,sticky="w")
    tk.Label(grid,text="2) DRIVING VIDEO (someone speaks/moves)",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=1,sticky="w",padx=(6,0))
    src_prev=tk.Label(grid,bg=CARD,text="(Preview)",fg=SUB,font=small_f,height=8); src_prev.grid(row=1,column=0,sticky="nsew",padx=(0,6),pady=4); src_prev._ref=None
    drv_box=tk.Label(grid,bg=CARD,text="(mp4 / mov / webm)",fg=SUB,font=small_f,height=8); drv_box.grid(row=1,column=1,sticky="nsew",padx=(6,0),pady=4)
    def pick_src():
        f=filedialog.askopenfilename(title="Choose photo",initialdir=os.path.expanduser("~\\Desktop"),
            filetypes=[("Images","*.png *.jpg *.jpeg *.webp"),("All","*.*")])
        if not f: return
        win._src=f; srcvar.set(os.path.basename(f)[:34])
        try:
            im=Image.open(f); im.thumbnail((250,250)); ph=ImageTk.PhotoImage(im); src_prev.config(image=ph,text=""); src_prev._ref=ph
        except: pass
    def pick_drv():
        f=filedialog.askopenfilename(title="Choose driving video",initialdir=os.path.expanduser("~\\Desktop"),
            filetypes=[("Videos","*.mp4 *.mov *.webm *.avi *.mkv"),("All","*.*")])
        if not f: return
        win._drv=f; drvvar.set(os.path.basename(f)[:34]); drv_box.config(text="\U0001f3ac\n"+os.path.basename(f)[:24])
    tk.Button(grid,text="\U0001f4c2 Choose photo",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=pick_src).grid(row=2,column=0,sticky="ew",padx=(0,6),pady=2)
    tk.Button(grid,text="\U0001f4c2 Choose video",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=pick_drv).grid(row=2,column=1,sticky="ew",padx=(6,0),pady=2)
    tk.Label(grid,textvariable=srcvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=0,sticky="w")
    tk.Label(grid,textvariable=drvvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=1,sticky="w",padx=(6,0))

    optf=tk.Frame(win,bg=BG); optf.pack(fill="x",padx=24,pady=(8,2))
    tk.Label(optf,text="Expressiveness: ",font=sub_f,bg=BG,fg=SUB).pack(side="left")
    EXPR={"Natural":1.0,"Subtle":0.7,"Strong":1.4}
    expr_var=tk.StringVar(value="Natural")
    ttk.Combobox(optf,textvariable=expr_var,values=list(EXPR.keys()),state="readonly",width=14).pack(side="left")

    go=tk.Button(win,text="\U0001f444  Bring photo to life",font=btn_f,bg=ACCENT,fg="#ffffff",relief="flat",cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff")
    go.pack(fill="x",padx=24,pady=(10,4))
    st=tk.Label(win,text="Tip: frontal photo + short driving video (3-8s) = best result. Slow on 1060.",font=sub_f,bg=BG,fg=GREEN,wraplength=600); st.pack(pady=(2,4))
    botf=tk.Frame(win,bg=BG); botf.pack(side="bottom",fill="x",pady=(6,12))
    def open_res():
        if win._last and os.path.exists(win._last): os.startfile(win._last)
        else: os.startfile(OUTPUT_DIR)
    tk.Button(botf,text="▶ Play video",font=sub_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=open_res).pack(side="left",expand=True,fill="x",padx=(24,6))
    tk.Button(botf,text="\U0001f4c1 Folder",font=sub_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",command=lambda:os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(6,24))

    def set_st(t): win.after(0,lambda:st.config(text=t))
    def done(path):
        win._last=path
        set_st("Done! "+os.path.basename(path)+" - opening...")
        try: os.startfile(path)
        except: pass
    def do_go():
        if not win._src: set_st("Please select a photo first (1)."); return
        if not win._drv: set_st("Please select a driving video first (2)."); return
        go.config(state="disabled",text="Bringing to life... (may take a while)")
        ex=EXPR.get(expr_var.get(),1.0)
        def worker():
            run_lipsync(win._src,win._drv,ex,set_st,done)
            win.after(0,lambda:go.config(state="normal",text="\U0001f444  Bring photo to life"))
        threading.Thread(target=worker,daemon=True).start()
    go.config(command=do_go)

# ---------- Code-RAG window (index & search your own code) ----------
def open_rag_window():
    win=tk.Toplevel(root); win.title("Overlkd - Code search"); win.configure(bg=BG)
    win.geometry("680x720"); win.minsize(580,600); win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Code search", win.destroy)
    tk.Label(win,text="\U0001f50e Code-RAG",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="Index your own projects and search them by meaning — 100% local, "
             "nothing leaves your machine.",font=small_f,bg=BG,fg=SUB,wraplength=620).pack(pady=(0,6))

    # --- service status row ---
    svc=tk.Frame(win,bg=BG); svc.pack(fill="x",padx=24,pady=(0,4))
    svc_dot=tk.Label(svc,text="●",font=small_f,bg=BG,fg=RED); svc_dot.pack(side="left")
    svc_lbl=tk.Label(svc,text=" Service: checking…",font=small_f,bg=BG,fg=SUB); svc_lbl.pack(side="left")
    svc_btn=tk.Button(svc,text="Start service",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2")
    svc_btn.pack(side="right")

    # --- indexed projects (live from /stats) ---
    pjf=tk.Frame(win,bg=BG); pjf.pack(fill="x",padx=24,pady=(0,4))
    tk.Label(pjf,text="INDEXED",font=small_f,bg=BG,fg=SUB).pack(side="left",anchor="n")
    proj_lbl=tk.Label(pjf,text="…",font=small_f,bg=BG,fg=ACCENT_LT,justify="left",
                      wraplength=560,anchor="w"); proj_lbl.pack(side="left",fill="x",expand=True,padx=(8,0))

    st=tk.Label(win,text="Ready.",font=sub_f,bg=BG,fg=GREEN,wraplength=620);
    def set_st(t): win.after(0,lambda:st.config(text=t))

    def running(): return port_open(cfg.rag_port)
    def need_service():
        if running(): return True
        set_st("Service is not running — click “Start service” first."); return False

    # --- add-to-index section ---
    idxf=tk.Frame(win,bg=BG); idxf.pack(fill="x",padx=24,pady=(4,2))
    tk.Label(idxf,text="ADD CODE TO THE INDEX",font=small_f,bg=BG,fg=ACCENT).pack(anchor="w",pady=(2,4))

    def _ingest(project,path):
        set_st(f"Indexing “{project}” … (first run may take a while)")
        try:
            env=dict(os.environ, MEMORY_API_URL=cfg.rag_api)
            r=subprocess.run([cfg.rag_python, os.path.join(RAG_DIR,"ingest.py"), project, path],
                             capture_output=True,text=True,env=env,timeout=3600,
                             creationflags=subprocess.CREATE_NO_WINDOW)
            lines=[l for l in ((r.stdout or "")+(r.stderr or "")).splitlines() if l.strip()]
            set_st(lines[-1] if lines else f"Indexed “{project}”.")
            win.after(0,refresh_projects)
        except Exception as e:
            set_st(f"Index error: {e}")

    def pick_and_index():
        if not need_service(): return
        path=filedialog.askdirectory(title="Choose a project folder to index",
                                     initialdir=os.path.expanduser("~"))
        if not path: return
        project=os.path.basename(path.rstrip("/\\")) or "project"
        threading.Thread(target=lambda:_ingest(project,path),daemon=True).start()

    idx_btn=tk.Button(idxf,text="\U0001f4c1  Index a project folder…",font=sub_f,bg=CARD,fg=FG,relief="flat",
              cursor="hand2",command=pick_and_index); idx_btn.pack(fill="x",pady=2)

    tk.Label(idxf,text="…or clone a public GitHub repo and index it:",font=small_f,bg=BG,fg=SUB).pack(anchor="w",pady=(8,2))
    ghf=tk.Frame(idxf,bg=BG); ghf.pack(fill="x")
    gh_var=tk.StringVar()
    gh_entry=tk.Entry(ghf,textvariable=gh_var,font=sub_f,bg=PANEL,fg=FG,insertbackground=FG,relief="flat")
    gh_entry.pack(side="left",fill="x",expand=True,ipady=5,padx=(0,6))

    def clone_and_index():
        if not need_service(): return
        url=gh_var.get().strip()
        if not url: set_st("Enter a GitHub repo URL first (e.g. https://github.com/user/repo)."); return
        def worker():
            name=url.rstrip("/").split("/")[-1]
            if name.endswith(".git"): name=name[:-4]
            name=name or "repo"
            repos=os.path.join(os.path.dirname(cfg.rag_data_dir),"repos")
            try: os.makedirs(repos,exist_ok=True)
            except Exception as e: set_st(f"Cannot create repos folder: {e}"); return
            dest=os.path.join(repos,name)
            set_st(f"Cloning {name} …")
            try:
                if os.path.isdir(os.path.join(dest,".git")):
                    subprocess.run(["git","-C",dest,"pull","--ff-only"],capture_output=True,text=True,
                                   timeout=900,creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    r=subprocess.run(["git","clone","--depth","1",url,dest],capture_output=True,text=True,
                                     timeout=900,creationflags=subprocess.CREATE_NO_WINDOW)
                    if r.returncode!=0:
                        set_st("Clone failed: "+(r.stderr or "").strip()[:140]); return
            except FileNotFoundError:
                set_st("git is not installed — install Git to clone repositories."); return
            except Exception as e:
                set_st(f"Clone error: {e}"); return
            _ingest(name,dest)
        threading.Thread(target=worker,daemon=True).start()

    clone_btn=tk.Button(ghf,text="⬇ Clone & index",font=sub_f,bg=ACCENT_DK,fg="#ffffff",relief="flat",
              cursor="hand2",command=clone_and_index); clone_btn.pack(side="right")

    # --- search section ---
    tk.Frame(win,bg=DIV,height=1).pack(fill="x",padx=24,pady=(10,6))
    srf=tk.Frame(win,bg=BG); srf.pack(fill="x",padx=24)
    tk.Label(srf,text="SEARCH YOUR CODE",font=small_f,bg=BG,fg=ACCENT).pack(anchor="w",pady=(0,4))
    qrow=tk.Frame(srf,bg=BG); qrow.pack(fill="x")
    q_var=tk.StringVar()
    q_entry=tk.Entry(qrow,textvariable=q_var,font=sub_f,bg=PANEL,fg=FG,insertbackground=FG,relief="flat")
    q_entry.pack(side="left",fill="x",expand=True,ipady=6,padx=(0,6))

    outf=tk.Frame(win,bg=CARD); outf.pack(fill="both",expand=True,padx=24,pady=(8,4))
    sb=tk.Scrollbar(outf); sb.pack(side="right",fill="y")
    out=tk.Text(outf,bg=CARD,fg=FG,font=small_f,relief="flat",wrap="word",
                yscrollcommand=sb.set,padx=10,pady=8,height=11,bd=0,highlightthickness=0)
    out.pack(side="left",fill="both",expand=True); sb.config(command=out.yview)
    out.tag_config("src",foreground=ACCENT_LT,font=sub_f)
    out.tag_config("score",foreground=SUB)
    out.tag_config("body",foreground="#c8c8c8")
    out.insert("end","Results appear here.\n"); out.config(state="disabled")

    def do_search():
        if not need_service(): return
        q=q_var.get().strip()
        if not q: return
        set_st("Searching …")
        def worker():
            try:
                body=json.dumps({"project":"*","query":q,"top_k":8}).encode()
                req=urllib.request.Request(cfg.rag_api+"/search",data=body,
                                           headers={"Content-Type":"application/json"})
                data=json.loads(urllib.request.urlopen(req,timeout=30).read())
                res=data.get("results",[])
                def render():
                    out.config(state="normal"); out.delete("1.0","end")
                    if not res:
                        out.insert("end","No matches yet. Index a project or repo above, then search.\n","body")
                    for it in res:
                        src=it.get("source","?"); sc=it.get("score",0.0)
                        txt=(it.get("text","") or "").strip()
                        out.insert("end",f"{src}   ","src"); out.insert("end",f"{sc:.2f}\n","score")
                        out.insert("end",(txt[:420]+("…" if len(txt)>420 else ""))+"\n\n","body")
                    out.config(state="disabled")
                win.after(0,render); set_st(f"{len(res)} result(s).")
            except Exception as e:
                set_st(f"Search error: {e}")
        threading.Thread(target=worker,daemon=True).start()

    search_btn=tk.Button(qrow,text="\U0001f50e Search",font=sub_f,bg=ACCENT,fg="#ffffff",relief="flat",
              cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff",
              command=do_search); search_btn.pack(side="right")
    q_entry.bind("<Return>",lambda e:do_search())

    st.pack(side="bottom",pady=(2,10))

    # --- service control + polling ---
    def do_start_svc(visible=False):
        set_st("Starting Code-RAG service (hidden, no window). First run downloads the embed model (~90 MB).")
        start_rag_service(visible=visible)
        def wait_up():
            for _ in range(90):
                if running():
                    set_st("Service is up. Ready to index and search."); win.after(0,refresh_projects); return
                time.sleep(1)
            set_st("Service did not start — the RAG needs its Python deps. Run setup/install.py to create the "
                   "RAG venv, or Shift-click “Start service” to open a console and see the error.")
        threading.Thread(target=wait_up,daemon=True).start()
    def do_stop_svc():
        set_st("Stopping Code-RAG service…")
        stop_service_port(cfg.rag_port)
    # Shift-click the service button = start with a visible console (for debugging)
    svc_btn.bind("<Shift-Button-1>", lambda e: do_start_svc(visible=True))

    def refresh_projects():
        def worker():
            try:
                data=json.loads(urllib.request.urlopen(cfg.rag_api+"/stats",timeout=8).read())
                projs=[p for p in data.get("projects",[]) if p not in ("*",)]
                txt=(", ".join(projs)+f"   ({len(projs)})") if projs else "nothing indexed yet"
            except Exception:
                txt="(service not running)"
            win.after(0,lambda:proj_lbl.config(text=txt))
        threading.Thread(target=worker,daemon=True).start()
    refresh_projects()

    action_widgets=[idx_btn, gh_entry, clone_btn, q_entry, search_btn]
    def refresh_svc():
        if not win.winfo_exists(): return
        up=running()
        svc_dot.config(fg=GREEN if up else RED)
        svc_lbl.config(text=(f" Service: running on :{cfg.rag_port}" if up else " Service: stopped (Shift-click = console)"))
        svc_btn.config(state="normal",
                       text=("Stop service" if up else "Start service"),
                       command=(do_stop_svc if up else do_start_svc))
        for w in action_widgets:
            try: w.config(state="normal" if up else "disabled")
            except tk.TclError: pass
        win.after(2000,refresh_svc)
    refresh_svc()

# ---------- Setup / install window (one-click, no terminal) ----------
# Baseline timings on a GTX 1060 6GB (multiplier = 1.0). Displayed values scale
# with the detected hardware. All rough — real speed varies with model/settings.
def _setup_infer_op(name):
    n=(name or "").lower()
    if "flux" in n: return "flux"
    if "upscale" in n or "ultrasharp" in n or "4x" in n: return "upscale"
    if "reactor" in n or "swap" in n or "inswapper" in n or "buffalo" in n or "face" in n: return "faceswap"
    if "liveportrait" in n or "lip" in n or ("portrait" in n and "live" in n): return "lipsync"
    if any(k in n for k in ("sd1.5","sd15","dreamshaper","realistic","toonyou","safetensors")): return "sd15"
    return ""

def _setup_estimate(op, mult):
    # Returns a short rough estimate string (already incl. "~"), or "" if unknown.
    if not mult or mult<=0: return ""
    if op=="flux":     return f"~{240/mult:.0f} s/image"
    if op=="sd15":     return f"~{20/mult:.0f} s/image"
    if op=="upscale":  return f"~{180/mult:.0f} s for 4K"
    if op=="faceswap": return f"~{169/mult:.0f} s"
    if op=="lipsync":  return f"~{44/mult:.0f} s (40 frames)"
    if op=="llm":      return f"~{8*mult:.0f} tok/s"
    return ""

def _setup_fmt_size(mb):
    try: mb=float(mb)
    except Exception: return ""
    if mb<=0: return ""
    return f"{mb/1024:.1f} GB" if mb>=1024 else f"{mb:.0f} MB"

def _setup_load_models():
    """Return (groups, from_manifest). ``groups`` is a list of
    (group_label, [(name, size_mb, op), ...]). Sourced from
    setup/models.manifest.json if present, else a hardcoded fallback."""
    models=ollama=None; from_manifest=False
    mpath=os.path.join(_APPDIR,"setup","models.manifest.json")
    try:
        with open(mpath,"r",encoding="utf-8") as f:
            data=json.load(f)
        models=data.get("models") or []
        ollama=data.get("ollama") or []
        from_manifest=True
    except Exception:
        models=None; ollama=None
    if models is None:
        models=[
            {"name":"FLUX schnell (GGUF Q4)","approx_size_mb":6500,"op":"flux"},
            {"name":"DreamShaper v8 (SD1.5)","approx_size_mb":2000,"op":"sd15"},
            {"name":"Realistic Vision v6 (SD1.5)","approx_size_mb":2000,"op":"sd15"},
            {"name":"ToonYou v6 (SD1.5)","approx_size_mb":2000,"op":"sd15"},
            {"name":"4x-UltraSharp upscaler","approx_size_mb":67,"op":"upscale"},
            {"name":"ReActor face swap (inswapper_128 + buffalo_l)","approx_size_mb":600,"op":"faceswap"},
            {"name":"LivePortrait (lip sync)","approx_size_mb":500,"op":"lipsync"},
        ]
        ollama=[{"name":"qwen2.5-coder:7b","approx_size_mb":4700},
                {"name":"qwen3.5:9b","approx_size_mb":5500}]
    imgs=[]; vids=[]; llms=[]
    for m in (models or []):
        nm=m.get("name","?"); sz=m.get("approx_size_mb",0)
        op=m.get("op") or _setup_infer_op(nm)
        row=(nm,sz,op)
        (vids if op in ("faceswap","lipsync") else imgs).append(row)
    for o in (ollama or []):
        if isinstance(o,dict): nm=o.get("name","?"); sz=o.get("approx_size_mb",0)
        else: nm=str(o); sz=0
        llms.append((nm,sz,"llm"))
    groups=[]
    if imgs: groups.append(("IMAGES & UPSCALE",imgs))
    if vids: groups.append(("FACE & VIDEO",vids))
    if llms: groups.append(("LOCAL CHAT (LLM)",llms))
    return groups, from_manifest

def _write_config_key(section, key, value):
    """Merge ``{section: {key: value}}`` into config.json next to studio.py,
    preserving every other key, and return the path written. Reads the existing
    file if present (else starts from ``{}``) so the user's other overrides — and
    anything setup/install.py wrote — are never clobbered. Writes valid JSON."""
    cfg_path=os.path.join(_APPDIR,"config.json")
    data={}
    try:
        with open(cfg_path,"r",encoding="utf-8") as f:
            loaded=json.load(f)
        if isinstance(loaded,dict): data=loaded
    except Exception:
        data={}
    sec=data.get(section)
    if not isinstance(sec,dict): sec={}
    sec[key]=value; data[section]=sec
    with open(cfg_path,"w",encoding="utf-8") as f:
        json.dump(data,f,indent=2)
    return cfg_path

def open_setup_window():
    win=tk.Toplevel(root); win.title("Overlkd - Setup & install"); win.configure(bg=BG)
    win.geometry("720x760"); win.minsize(620,620); win.resizable(True,True)
    win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Setup & install", win.destroy)

    tk.Label(win,text="⚙ Setup & install",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="One click installs everything — no terminal needed.",
             font=small_f,bg=BG,fg=SUB,wraplength=660).pack(pady=(0,2))
    req_link=tk.Label(win,text="📋 Requirements & licenses",font=small_f,bg=BG,fg=ACCENT_LT,cursor="hand2")
    req_link.pack(pady=(0,6)); req_link.bind("<Button-1>",lambda e:open_requirements_window())

    # --- Fixed status bar at the bottom: always visible, never scrolls away ---
    fixed_st=tk.Label(win,text="Ready.",font=sub_f,bg=PANEL,fg=GREEN,anchor="w",
                      wraplength=680,justify="left",padx=12,pady=8)
    fixed_st.pack(side="bottom",fill="x")

    # --- Scrollable body: content can exceed the window; scroll with wheel / scrollbar ---
    _scwrap=tk.Frame(win,bg=BG); _scwrap.pack(fill="both",expand=True)
    _canvas=tk.Canvas(_scwrap,bg=BG,highlightthickness=0)
    _vsb=tk.Scrollbar(_scwrap,orient="vertical",command=_canvas.yview)
    _canvas.configure(yscrollcommand=_vsb.set)
    _vsb.pack(side="right",fill="y"); _canvas.pack(side="left",fill="both",expand=True)
    body=tk.Frame(_canvas,bg=BG)
    _bid=_canvas.create_window((0,0),window=body,anchor="nw")
    body.bind("<Configure>",lambda e:_canvas.configure(scrollregion=_canvas.bbox("all")))
    _canvas.bind("<Configure>",lambda e:_canvas.itemconfig(_bid,width=e.width))
    def _wheel(e):
        try: _canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        except Exception: pass
    win.bind("<MouseWheel>",_wheel)

    # --- A) Hardware check ---
    hwcard=tk.Frame(body,bg=CARD); hwcard.pack(fill="x",padx=24,pady=(0,6))
    hw_lbl=tk.Label(hwcard,text="Detecting hardware…",font=sub_f,bg=CARD,fg=ACCENT_LT,
                    anchor="w",wraplength=560,justify="left")
    hw_lbl.pack(side="left",fill="x",expand=True,padx=10,pady=8)
    redet=tk.Label(hwcard,text="↻ Re-detect",font=small_f,bg=CARD,fg=SUB,cursor="hand2")
    redet.pack(side="right",padx=10)

    # --- A2) Install location (which drive/folder everything goes on) ---
    loc_card=tk.Frame(body,bg=CARD); loc_card.pack(fill="x",padx=24,pady=(0,6))
    tk.Label(loc_card,text="INSTALL LOCATION",font=small_f,bg=CARD,fg=ACCENT).pack(anchor="w",padx=10,pady=(8,0))
    loc_root_lbl=tk.Label(loc_card,text="",font=sub_f,bg=CARD,fg=FG,anchor="w",wraplength=640,justify="left")
    loc_root_lbl.pack(anchor="w",fill="x",padx=10,pady=(1,0))
    loc_paths_lbl=tk.Label(loc_card,text="",font=small_f,bg=CARD,fg=SUB,anchor="w",wraplength=640,justify="left")
    loc_paths_lbl.pack(anchor="w",fill="x",padx=10,pady=(1,0))
    loc_status_lbl=tk.Label(loc_card,text="",font=small_f,bg=CARD,fg=GREEN,anchor="w",wraplength=640,justify="left")
    loc_status_lbl.pack(anchor="w",fill="x",padx=10,pady=(1,0))
    locrow=tk.Frame(loc_card,bg=CARD); locrow.pack(fill="x",padx=10,pady=(4,2))
    choose_btn=tk.Button(locrow,text="📁  Choose folder…",font=sub_f,bg=ACCENT,fg="#ffffff",relief="flat",
                         cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff")
    choose_btn.pack(side="left")
    tk.Label(loc_card,text="Pick a drive with ~100 GB free. Leave as Auto to use the default.",
             font=small_f,bg=CARD,fg=SUB,anchor="w",wraplength=640,justify="left").pack(anchor="w",padx=10,pady=(2,8))

    def _loc_render(root_dir):
        # Update the read-out from a root path directly (no cfg reload needed).
        # root_dir="" -> Auto: show the currently derived comfy_dir / qdrant_path.
        if root_dir:
            loc_root_lbl.config(text="Current: "+root_dir)
            models_p=os.path.join(root_dir,"comfyui")
            rag_p=os.path.join(root_dir,"VultureAI","rag")
            loc_paths_lbl.config(text=f"Models → {models_p}   ·   RAG → {rag_p}")
        else:
            loc_root_lbl.config(text="Current: Auto (%LOCALAPPDATA% / detected drive)")
            loc_paths_lbl.config(text=f"Models → {cfg.comfy_dir or '(installs on detected drive)'}"
                                      f"   ·   RAG → {cfg.qdrant_path}")
    def choose_location():
        d=filedialog.askdirectory(title="Choose where to install models + RAG",
                                  initialdir=cfg.install_base or _APPDIR)
        if not d: return
        d=os.path.normpath(d)
        try:
            _write_config_key("paths","install_base",d)
            _loc_render(d)
            loc_status_lbl.config(fg=GREEN,text="Saved. Models + RAG will install under: "
                                                f"{d}  (applies to the install below).")
        except Exception as e:
            loc_status_lbl.config(fg=RED,text=f"Could not save location: {e}")
    choose_btn.config(command=choose_location)
    _loc_render(cfg.install_base)

    # --- B) Model list with hardware-scaled speed estimates ---
    groups,from_manifest=_setup_load_models()
    models_frame=tk.Frame(body,bg=BG); models_frame.pack(fill="x",padx=24,pady=(0,4))
    def render_models(mult):
        for w in models_frame.winfo_children():
            try: w.destroy()
            except Exception: pass
        tk.Label(models_frame,text="Estimated on YOUR hardware (rough — real speed varies) · click a group to expand:",
                 font=small_f,bg=BG,fg=SUB,wraplength=640,justify="left").pack(anchor="w",pady=(2,4))
        for gname,rows in groups:
            gframe=tk.Frame(models_frame,bg=BG); gframe.pack(fill="x",pady=(3,0))
            hdr=tk.Label(gframe,text=f"▸  {gname}   ({len(rows)})",font=small_f,bg=CARD,fg=ACCENT_LT,
                         anchor="w",cursor="hand2",padx=10,pady=5)
            hdr.pack(fill="x")
            rowsfr=tk.Frame(gframe,bg=BG)  # collapsed by default (not packed yet)
            for nm,sz,op in rows:
                est=_setup_estimate(op,mult); size=_setup_fmt_size(sz)
                parts=[p for p in (nm,size,est) if p]
                tk.Label(rowsfr,text="   "+"  ·  ".join(parts),font=small_f,
                         bg=BG,fg=FG,anchor="w",wraplength=610,justify="left").pack(anchor="w")
            def _toggle(e=None,rf=rowsfr,h=hdr,gn=gname,n=len(rows),st={"open":False}):
                st["open"]=not st["open"]
                if st["open"]: rf.pack(fill="x",padx=(6,0),pady=(2,5)); h.config(text=f"▾  {gn}   ({n})")
                else: rf.pack_forget(); h.config(text=f"▸  {gn}   ({n})")
            hdr.bind("<Button-1>",_toggle)

    def detect_worker():
        gpu=detect_gpu(); ram=detect_ram_gb()
        mult=speed_multiplier(gpu.get("vram_gb",0.0), gpu.get("name",""))
        def apply():
            if not win.winfo_exists(): return
            if gpu.get("name"):
                hw_lbl.config(text=f"GPU: {gpu['name']} · {gpu['vram_gb']:.0f} GB VRAM"
                                   f"   |   RAM: {ram:.0f} GB")
            else:
                hw_lbl.config(text="No NVIDIA GPU detected (CPU mode — very slow)"
                                   f"   |   RAM: {ram:.0f} GB")
            render_models(mult)
        win.after(0,apply)
    def redetect():
        hw_lbl.config(text="Detecting hardware…")
        threading.Thread(target=detect_worker,daemon=True).start()
    redet.bind("<Button-1>",lambda e:redetect())

    tk.Frame(body,bg=DIV,height=1).pack(fill="x",padx=24,pady=(8,6))

    # --- C) One-click install (streams the installer output, no terminal) ---
    INSTALLER=os.path.join(_APPDIR,"setup","install.py")
    have_installer=os.path.exists(INSTALLER)

    st=tk.Label(body,text="Ready." if have_installer else "Installer not found.",
                font=sub_f,bg=BG,fg=GREEN,wraplength=660)
    def set_st(t, busy=False, color=None):
        def _apply():
            fixed_st.config(text=t, fg=(color or (ACCENT_LT if busy else GREEN)))
            try: st.config(text=t)
            except Exception: pass
        win.after(0,_apply)

    btnrow=tk.Frame(body,bg=BG); btnrow.pack(fill="x",padx=24,pady=(2,2))
    install_btn=tk.Button(btnrow,text="⤓  Install everything",font=btn_f,bg=ACCENT,fg="#ffffff",
                          relief="flat",cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff")
    install_btn.pack(fill="x",pady=(0,4))
    check_btn=tk.Button(btnrow,text="🔍  Check what's missing",font=sub_f,bg=CARD,fg=ACCENT_LT,
                        relief="flat",cursor="hand2",activebackground=PANEL,activeforeground=FG)
    check_btn.pack(fill="x")
    tk.Label(btnrow,text="Installs go to the location chosen above (Auto = default drive).",
             font=small_f,bg=BG,fg=SUB,anchor="w",wraplength=660,justify="left").pack(fill="x",pady=(3,0))

    tk.Label(btnrow,text="Everything else installs by default and is fine for commercial use. See 📋 Licenses.",
             font=small_f,bg=BG,fg=SUB,anchor="w",wraplength=660,justify="left").pack(fill="x",pady=(6,0))

    # --- Manual models: non-commercial, the USER downloads these (Vulture NEVER does) ---
    # Populated from `install.py --manual-list` (one MANUAL\t… line per model). Every
    # widget update happens on the Tk main thread via win.after; the subprocess runs
    # in a worker thread so the window never blocks.
    man_card=tk.Frame(body,bg=CARD); man_card.pack(fill="x",padx=24,pady=(8,6))
    manhdr=tk.Frame(man_card,bg=CARD); manhdr.pack(fill="x",padx=10,pady=(8,0))
    tk.Label(manhdr,text="📥 Manual models — you download these (non-commercial)",
             font=small_f,bg=CARD,fg=ACCENT).pack(side="left")
    man_recheck=tk.Label(manhdr,text="↻ Re-check",font=small_f,bg=CARD,fg=SUB,cursor="hand2")
    man_recheck.pack(side="right")
    tk.Label(man_card,text="Vulture never downloads these — their licenses are personal / "
             "research use only. Get them yourself, drop them in the folder, then Re-check.",
             font=small_f,bg=CARD,fg=SUB,anchor="w",wraplength=640,justify="left").pack(
             anchor="w",fill="x",padx=10,pady=(1,4))
    man_rows=tk.Frame(man_card,bg=CARD); man_rows.pack(fill="x",padx=10,pady=(0,8))

    def _man_open_folder(target):
        # Open the folder to drop the file/pack into. For a FILE target (...\x.pth) that
        # is the parent dir; for a FOLDER target (...\buffalo_l, ...\liveportrait) it is
        # the folder ITSELF -- so users extract INTO it, not one level too high.
        try:
            # Guard: never create stray relative folders (happens if ComfyUI isn't
            # configured yet -> the target is a bare relative path). Install first.
            if not os.path.isabs(target): return
            base=os.path.basename(target.rstrip("\\/"))
            is_file=("." in base and base.rsplit(".",1)[1].lower()
                     in ("pth","onnx","safetensors","ckpt","bin","zip","gguf"))
            d=os.path.dirname(target) if is_file else target
            os.makedirs(d,exist_ok=True); os.startfile(d)
        except Exception: pass
    def _man_render(items):
        # (main thread) rebuild the rows. items: None = loading, str = error, list = models.
        for w in man_rows.winfo_children():
            try: w.destroy()
            except Exception: pass
        if items is None:
            tk.Label(man_rows,text="Checking…",font=small_f,bg=CARD,fg=SUB).pack(anchor="w"); return
        if isinstance(items,str):
            tk.Label(man_rows,text=items,font=small_f,bg=CARD,fg=RED,anchor="w",
                     wraplength=620,justify="left").pack(anchor="w"); return
        if not items:
            tk.Label(man_rows,text="No manual models needed. ✓",font=small_f,bg=CARD,fg=GREEN).pack(anchor="w"); return
        for it in items:
            row=tk.Frame(man_rows,bg=CARD); row.pack(fill="x",pady=2)
            tk.Label(row,text="●",font=small_f,bg=CARD,fg=GREEN if it["present"] else RED).pack(side="left")
            fold=tk.Label(row,text="📂 Folder",font=small_f,bg=CARD,fg=ACCENT_LT,cursor="hand2"); fold.pack(side="right",padx=(6,0))
            fold.bind("<Button-1>",lambda e,t=it["target"]:_man_open_folder(t))
            get=tk.Label(row,text="🔗 Get it",font=small_f,bg=CARD,fg=ACCENT_LT,cursor="hand2"); get.pack(side="right",padx=(6,0))
            get.bind("<Button-1>",lambda e,u=it["page"]:webbrowser.open(u))
            meta=tk.Frame(row,bg=CARD); meta.pack(side="left",fill="x",expand=True,padx=(4,0))
            tk.Label(meta,text=it["name"],font=small_f,bg=CARD,fg=FG,anchor="w").pack(anchor="w")
            tk.Label(meta,text=it["license"],font=small_f,bg=CARD,fg=SUB,anchor="w").pack(anchor="w")
            if it.get("note"):
                tk.Label(meta,text=it["note"],font=small_f,bg=CARD,fg=ACCENT_LT,anchor="w",
                         wraplength=540,justify="left").pack(anchor="w")
    def _man_refresh():
        if not have_installer:
            _man_render("Installer not found — cannot list manual models."); return
        _man_render(None)
        def worker():
            try:
                py=cfg.system_python or sys.executable
                out=subprocess.run([py, INSTALLER, "--manual-list"], cwd=_APPDIR,
                    capture_output=True, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW).stdout or ""
                items=[]
                for line in out.splitlines():
                    if not line.startswith("MANUAL\t"): continue
                    parts=line.split("\t")
                    if len(parts)<6: continue
                    _tag,name,lic,page,target,present=parts[:6]
                    note=parts[6] if len(parts)>=7 else ""
                    items.append({"name":name,"license":lic,"page":page,
                                  "target":target,"present":present.strip()=="1","note":note})
                win.after(0,lambda:_man_render(items))
            except Exception as e:
                win.after(0,lambda m=str(e):_man_render("Could not list manual models: "+m))
        threading.Thread(target=worker,daemon=True).start()
    man_recheck.bind("<Button-1>",lambda e:_man_refresh())

    note_lbl=tk.Label(body,font=small_f,bg=BG,fg=SUB,wraplength=660,justify="left")
    if not have_installer:
        note_lbl.config(text="Installer not found — this looks like a dev copy. In a fresh "
                             "`git clone` the setup/ folder is present.")
        note_lbl.pack(fill="x",padx=24,pady=(4,2))

    # --- output log (read-only, dark; like the Code-RAG results box) ---
    outf=tk.Frame(body,bg=CARD); outf.pack(fill="x",padx=24,pady=(6,4))
    sb=tk.Scrollbar(outf); sb.pack(side="right",fill="y")
    log=tk.Text(outf,bg=CARD,fg="#c8c8c8",font=("Consolas",9),relief="flat",wrap="word",
                yscrollcommand=sb.set,padx=10,pady=8,height=10,bd=0,highlightthickness=0)
    log.pack(side="left",fill="both",expand=True); sb.config(command=log.yview)
    log.insert("end","Install progress will appear here.\n"); log.config(state="disabled")
    st.pack(pady=(2,10))

    def _log(s):
        def _do():
            if not win.winfo_exists(): return
            log.config(state="normal"); log.insert("end",s); log.see("end"); log.config(state="disabled")
        win.after(0,_do)
    def _log_clear():
        def _do():
            if not win.winfo_exists(): return
            log.config(state="normal"); log.delete("1.0","end"); log.config(state="disabled")
        win.after(0,_do)

    def run_installer(args, label, start_msg=None):
        # Stream `python setup/install.py [args]` line-by-line into the log box.
        # All subprocess reads happen here in the worker thread; every widget
        # update goes through win.after -> the Tk main thread is never blocked.
        def worker():
            win.after(0,lambda:(install_btn.config(state="disabled"),check_btn.config(state="disabled")))
            set_st(start_msg or (label+" running… live progress in the log below ↓"), busy=True)
            win.after(0,lambda:(_canvas.update_idletasks(), _canvas.yview_moveto(1.0)))  # reveal the log
            _log_clear()
            py=cfg.system_python or sys.executable
            _log(f"$ \"{py}\" setup/install.py {' '.join(args)}\n\n")
            try:
                proc=subprocess.Popen([py, INSTALLER]+list(args), cwd=_APPDIR,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                    bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
                for line in iter(proc.stdout.readline, ""):
                    _log(line)
                proc.stdout.close()
                code=proc.wait()
                _log(f"\n[exit {code}] "+("done." if code==0 else "finished with errors.")+"\n")
                set_st(f"{label} finished (exit {code}).")
            except Exception as e:
                _log(f"\n[error] {e}\n"); set_st(f"{label} error: {e}")
            finally:
                win.after(0,lambda:(install_btn.config(state="normal"),check_btn.config(state="normal")))
        threading.Thread(target=worker,daemon=True).start()

    # Ollama prerequisite gate: the real install pulls the local LLMs, so Ollama must
    # be present first. The "Check what's missing" (--list) button stays available.
    OLLAMA_EXE=os.path.join(os.environ.get("LOCALAPPDATA",""),"Programs","Ollama","ollama.exe")
    def _ollama_ready():
        return port_open(cfg.ollama_port) or os.path.exists(OLLAMA_EXE)
    def do_install():
        if not _ollama_ready():
            set_st("Install the Ollama desktop app first (ollama.com) — Vulture needs it for the local LLMs.")
            return
        run_installer([], "Install",
            "Installing… downloading ComfyUI + tens of GB of models — this can take 30–90 min "
            "depending on your connection. Live progress in the log below ↓.")
    def do_check():
        args=["--list"]
        run_installer(args, "Check")

    if have_installer:
        install_btn.config(command=do_install)
        check_btn.config(command=do_check)
    else:
        install_btn.config(state="disabled"); check_btn.config(state="disabled")

    redetect()  # auto-run the hardware check on open
    _man_refresh()  # auto-list the manual (non-commercial) models on open

# ---------- First-run Requirements & licenses window ----------
# Vulture is a launcher: it must NOT hide the prerequisites the user installs
# themselves, what it downloads from original sources, or the non-commercial
# model licenses. Shown once on first launch (until "I understand"), and always
# reachable from the footer "📋 Licenses" link and inside ⚙ Setup.
def open_requirements_window(first_run=False):
    win=tk.Toplevel(root); win.title("Overlkd - Requirements & licenses"); win.configure(bg=BG)
    win.geometry("720x780"); win.minsize(620,620); win.resizable(True,True)
    win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Requirements & licenses", win.destroy)

    # --- Fixed header ---
    tk.Label(win,text="📋 Requirements & licenses",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="Vulture is a launcher — you install the tools, it runs them. Please read once.",
             font=small_f,bg=BG,fg=SUB,wraplength=660).pack(pady=(0,6))

    # --- Fixed footer (packed before the scroll body so it stays visible) ---
    footer=tk.Frame(win,bg=BG); footer.pack(side="bottom",fill="x")
    def _ack_and_setup():
        try: _write_config_key("runtime","requirements_ack",True)
        except Exception: pass
        win.destroy()
        root.after(200, open_setup_window)   # continue straight to the install screen
    def _ack_close():
        try: _write_config_key("runtime","requirements_ack",True)
        except Exception: pass
        win.destroy()
    _btxt = "✓  I understand — continue to Setup" if first_run else "✓  I understand — close"
    ack_btn=tk.Button(footer,text=_btxt,font=btn_f,bg=ACCENT,fg="#ffffff",
                      relief="flat",cursor="hand2",activebackground=ACCENT_DK,activeforeground="#ffffff",
                      command=(_ack_and_setup if first_run else _ack_close))
    ack_btn.pack(fill="x",padx=24,pady=(8,2))
    tk.Label(footer,text=("Next step → ⚙ Setup: pick your drive, then Install everything." if first_run
                          else "You can reopen this anytime from ⚙ Setup."),
             font=small_f,bg=BG,fg=(ACCENT_LT if first_run else SUB)).pack(pady=(0,10))

    # --- Scrollable body: content is long (same pattern as open_setup_window) ---
    _scwrap=tk.Frame(win,bg=BG); _scwrap.pack(fill="both",expand=True)
    _canvas=tk.Canvas(_scwrap,bg=BG,highlightthickness=0)
    _vsb=tk.Scrollbar(_scwrap,orient="vertical",command=_canvas.yview)
    _canvas.configure(yscrollcommand=_vsb.set)
    _vsb.pack(side="right",fill="y"); _canvas.pack(side="left",fill="both",expand=True)
    body=tk.Frame(_canvas,bg=BG)
    _bid=_canvas.create_window((0,0),window=body,anchor="nw")
    body.bind("<Configure>",lambda e:_canvas.configure(scrollregion=_canvas.bbox("all")))
    _canvas.bind("<Configure>",lambda e:_canvas.itemconfig(_bid,width=e.width))
    def _wheel(e):
        try: _canvas.yview_scroll(int(-1*(e.delta/120)),"units")
        except Exception: pass
    win.bind("<MouseWheel>",_wheel)

    # === Section 1 — install these yourself first (with live detection) ===
    sec1=tk.Frame(body,bg=CARD); sec1.pack(fill="x",padx=24,pady=(0,6))
    s1head=tk.Frame(sec1,bg=CARD); s1head.pack(fill="x",padx=10,pady=(8,2))
    tk.Label(s1head,text="① Install these yourself first",font=sub_f,bg=CARD,fg=ACCENT).pack(side="left")
    recheck=tk.Label(s1head,text="↻ Re-check",font=small_f,bg=CARD,fg=SUB,cursor="hand2"); recheck.pack(side="right")
    rows_frame=tk.Frame(sec1,bg=CARD); rows_frame.pack(fill="x",padx=10,pady=(0,8))

    req_rows={}
    def _req_row(key,name,why,url=None):
        r=tk.Frame(rows_frame,bg=CARD); r.pack(fill="x",pady=2)
        dot=tk.Label(r,text="●",font=small_f,bg=CARD,fg=SUB); dot.pack(side="left")
        base=f" {name} — {why}"
        txt=tk.Label(r,text=base+"  (checking…)",font=small_f,bg=CARD,fg=FG,anchor="w",
                     wraplength=500,justify="left"); txt.pack(side="left",fill="x",expand=True)
        if url:
            link=tk.Label(r,text="Get it ↗",font=small_f,bg=CARD,fg=ACCENT_LT,cursor="hand2")
            link.pack(side="right"); link.bind("<Button-1>",lambda e,u=url:webbrowser.open(u))
        req_rows[key]=(dot,txt,base)
    def _set_row(key,ok,detail):
        d=req_rows.get(key)
        if not d: return
        dot,txt,base=d
        dot.config(fg=GREEN if ok else RED)
        txt.config(text=base+(f"  ({detail})" if detail else ""))

    _req_row("gpu","NVIDIA GPU + driver","for GPU-accelerated image generation",
             "https://www.nvidia.com/Download/index.aspx")
    _req_row("python","Python 3.11 (64-bit)","runs Vulture and the tools",
             "https://www.python.org/downloads/")
    _req_row("git","Git","clone & update repos and tools","https://git-scm.com/download/win")
    _req_row("ollama","Ollama desktop app","Vulture pulls the LLMs into it",
             "https://ollama.com/download")
    _req_row("disk","~100 GB free disk","the models are large")

    def _detect():
        out={}
        try: out["gpu"]=(detect_gpu().get("name","") or "")
        except Exception: out["gpu"]=""
        out["python"]=bool(shutil.which("python"))
        out["git"]=bool(shutil.which("git"))
        exe=os.path.join(os.environ.get("LOCALAPPDATA",""),"Programs","Ollama","ollama.exe")
        try: out["ollama"]=bool(port_open(11434) or os.path.exists(exe))
        except Exception: out["ollama"]=os.path.exists(exe)
        try: out["free_gb"]=shutil.disk_usage(_APPDIR).free/(1024**3)
        except Exception: out["free_gb"]=0.0
        def apply():
            if not win.winfo_exists(): return
            gn=out["gpu"]
            _set_row("gpu",bool(gn),gn or "not detected")
            _set_row("python",out["python"],"found" if out["python"] else "not found — install it")
            _set_row("git",out["git"],"found" if out["git"] else "not found — install it")
            _set_row("ollama",out["ollama"],"detected" if out["ollama"] else "not detected")
            fg=out["free_gb"]
            _set_row("disk",fg>=100,f"{fg:.0f} GB free" if fg>0 else "unknown")
        win.after(0,apply)
    def recheck_now():
        for k,(dot,txt,base) in req_rows.items():
            dot.config(fg=SUB); txt.config(text=base+"  (checking…)")
        threading.Thread(target=_detect,daemon=True).start()
    recheck.bind("<Button-1>",lambda e:recheck_now())

    # === Section 2 — what Vulture downloads & launches for you ===
    sec2=tk.Frame(body,bg=CARD); sec2.pack(fill="x",padx=24,pady=(0,6))
    tk.Label(sec2,text="② What Vulture downloads & launches for you",
             font=sub_f,bg=CARD,fg=ACCENT).pack(anchor="w",padx=10,pady=(8,2))
    tk.Label(sec2,text="Nothing is bundled — Vulture downloads each tool/model from its original source "
             "and runs tools as separate processes, so you accept each project's own license.",
             font=small_f,bg=CARD,fg=FG,anchor="w",wraplength=640,justify="left").pack(anchor="w",padx=10,pady=(0,4))
    for _ln in ("• ComfyUI (image backend) — GPL-3.0, launched as a separate process",
                "• Models from HuggingFace & original repos (FLUX, SD1.5, face, upscaler)",
                "• Local LLMs via `ollama pull` (Qwen, DeepSeek)"):
        tk.Label(sec2,text=_ln,font=small_f,bg=CARD,fg=SUB,anchor="w",
                 wraplength=640,justify="left").pack(anchor="w",padx=16,pady=1)
    tk.Frame(sec2,bg=CARD,height=6).pack()

    # === Section 3 — licenses (most commercial-OK, a few models are NOT) ===
    sec3=tk.Frame(body,bg=CARD); sec3.pack(fill="x",padx=24,pady=(0,6))
    tk.Label(sec3,text="③ Licenses — most is free for commercial use, a few models are NOT",
             font=sub_f,bg=CARD,fg=ACCENT,anchor="w",wraplength=640,justify="left").pack(anchor="w",padx=10,pady=(8,4))
    tk.Label(sec3,text="✅ Commercial-OK: FLUX.1-schnell (the default image model — you own your images), "
             "SD1.5 checkpoints, the local LLMs (Qwen / DeepSeek), Ollama, Aider, ComfyUI.",
             font=small_f,bg=CARD,fg=GREEN,anchor="w",wraplength=640,justify="left").pack(anchor="w",padx=10,pady=(0,6))
    tk.Label(sec3,text="⛔ Personal / research only (their authors' rule — NOT for commercial products):",
             font=sub_f,bg=CARD,fg=RED,anchor="w",wraplength=640,justify="left").pack(anchor="w",padx=10,pady=(2,2))
    for _ln in ("• Face swap — InsightFace models (inswapper_128 + buffalo_l)",
                "• Face restore — CodeFormer (S-Lab license)",
                "• 4x-UltraSharp upscaler (CC-BY-NC-SA) — swap to a permissive upscaler for commercial work",
                "• FLUX.1-dev — if you switch off the schnell default",
                "• LivePortrait — ships the non-commercial InsightFace detector"):
        tk.Label(sec3,text=_ln,font=small_f,bg=CARD,fg=SUB,anchor="w",
                 wraplength=630,justify="left").pack(anchor="w",padx=16,pady=1)
    tk.Label(sec3,text="Open WebUI's name/logo must stay visible (don't white-label its chat).",
             font=small_f,bg=CARD,fg=SUB,anchor="w",wraplength=640,justify="left").pack(anchor="w",padx=10,pady=(6,2))
    notice=tk.Label(sec3,text="Open the full license notes (NOTICE) ↗",
                    font=small_f,bg=CARD,fg=ACCENT_LT,cursor="hand2")
    notice.pack(anchor="w",padx=10,pady=(2,8))
    def _open_notice(e=None):
        try: os.startfile(os.path.join(_APPDIR,"NOTICE"))
        except Exception: pass
    notice.bind("<Button-1>",_open_notice)

    recheck_now()  # run the live detection on open (threaded, non-blocking)

# --- First run: show Requirements & licenses once (until acknowledged) ---
try: _req_ack=bool(cfg._r("requirements_ack"))
except Exception: _req_ack=False
if not _req_ack:
    root.after(500, lambda: open_requirements_window(first_run=True))

root.mainloop()
