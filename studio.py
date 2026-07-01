# -*- coding: utf-8 -*-
"""OVRLKD Studio AI - One window for everything, incl. a simple image generator."""
import tkinter as tk
from tkinter import font as tkfont, ttk, messagebox, filedialog
import subprocess, socket, os, threading, webbrowser, json, urllib.request, time, random, io

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find the vulture pkg
from vulture.config import get_config
cfg = get_config()

# --- was hard-coded, now from config.json / auto-detect ---
COMFY_PY   = cfg.comfy_python          # was r"D:\comfyui\venv\Scripts\python.exe"
COMFY_API  = cfg.comfy_api             # was "http://127.0.0.1:8188"
OUTPUT_DIR = cfg.output_dir            # was r"D:\comfyui\output"
TOOLS      = cfg.tools_dir             # was r"C:\Users\User\ai-memory-tools"

# ---- OVRLKD editorial dark-purple palette ----
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

SERVICES = cfg.services

NEG = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, worst quality, low quality, jpeg artifacts, signature, watermark, blurry, ugly, deformed, mutated"

# Model -> (engine, file)  -- FLUX is the default (best quality)
MODELS = {
    "FLUX  (best quality)":            ("flux", cfg.model_flux_unet),
    "DreamShaper  (fast/draft)":       ("sd15", "DreamShaper_v8.safetensors"),
    "Realistic Vision  (photo, fast)": ("sd15","RealisticVision_v6.safetensors"),
    "ToonYou  (cartoon, fast)":        ("sd15", "ToonYou_v6.safetensors"),
}
# Suffix for character mode (3D/rigging): A-pose, full body, straight
CHAR_SUFFIX = (", full body character, standing straight in A-pose, arms slightly "
    "away from body, front view, symmetrical, neutral pose, full figure from head to toe, "
    "character reference sheet, plain solid grey background, even lighting, T-pose")
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
    run_hidden(f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {cfg.comfy_port},{cfg.webui_port},{cfg.rag_port},{cfg.tunnel_port} -State Listen -EA SilentlyContinue | %% {{ Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }}"')

def start_webui_and_open():
    if not port_open(cfg.webui_port): run_hidden(f'"{os.path.join(cfg.tools_dir, "start-webui.cmd")}"')
    webbrowser.open(cfg.webui_url)
def _open_cmd(path):
    # reliably open a console window (os.startfile launches the .cmd in its own window)
    try: os.startfile(path)
    except Exception:
        subprocess.Popen(f'start "OVRLKD" "{path}"', shell=True)
def open_coder(): _open_cmd(cfg.coder_cmd)
def open_status(): _open_cmd(cfg.status_cmd)
def open_3d():
    if os.path.exists(os.path.join(cfg.tripo_src_dir, "run.py")): _open_cmd(os.path.join(cfg.tripo_dir, "Bild-zu-3D.cmd"))
    else: _open_cmd(os.path.join(cfg.tripo_dir, "1-Setup-3D-installieren.cmd"))

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
root.geometry("900x540+140+80"); root.minsize(820,500); root.resizable(True,True)

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
    win=tk.Toplevel(root); win.title("OVRLKD - Support"); win.geometry("440x400")
    win.lift(); win.focus_force()
    make_frameless(win, "♥  Support", win.destroy)
    tk.Label(win,text="Support keeps it free & offline.",font=sub_f,bg=BG,fg=ACCENT_LT).pack(pady=(16,4))
    tk.Label(win,text="Copy an address to send a tip - thank you.",font=small_f,bg=BG,fg=SUB).pack(pady=(0,10))
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
_by=tk.Label(head,text="  by OVRLKD Studio ↗",font=sub_f,bg=BG,fg=ACCENT_LT,cursor="hand2"); _by.pack(side="left",pady=(10,0))
_by.bind("<Button-1>",lambda e:webbrowser.open("https://www.overlkd.com"))
tk.Frame(root,bg=DIV,height=1).pack(fill="x",padx=24,pady=(0,2))

# ---- Footer: rotating slogan + subtle support link ----
foot=tk.Frame(root,bg=BG); foot.pack(side="bottom",fill="x",padx=24,pady=(0,8))
slogan_lbl=tk.Label(foot,text=SLOGANS[0],font=small_f,bg=BG,fg=SUB); slogan_lbl.pack(side="left")
sup_lbl=tk.Label(foot,text="♥ Support",font=small_f,bg=BG,fg=ACCENT_LT,cursor="hand2"); sup_lbl.pack(side="right")
sup_lbl.bind("<Button-1>",lambda e:open_support_window())
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
for i in range(5): left.rowconfigure(i,weight=1)

# Start spans the full width
make_card(left,0,0,"▶","START ALL","Boot up services",start_all,base=ACCENT,fg="#ffffff").grid(columnspan=2,sticky="nsew")
make_card(left,1,0,"\U0001f3a8","Create images","Text in, image out",lambda:open_generator())
make_card(left,1,1,"\U0001f4ac","Chat","Local AI models",start_webui_and_open)
make_card(left,2,0,"\U0001f4bb","Coding agent","Aider (terminal)",open_coder)
make_card(left,2,1,"\U0001f9ca","Image → 3D","Photo -> 3D model",lambda:open_3d_window())
make_card(left,3,0,"\U0001f3c3","Rig/Animate","Mixamo (browser)",lambda:webbrowser.open("https://www.mixamo.com"))
make_card(left,3,1,"\U0001f4ca","Status","RAM / VRAM / GPU",open_status)
make_card(left,4,0,"\U0001f3ad","Face swap","Face swap (photo)",lambda:open_faceswap_window())
make_card(left,4,1,"\U0001f444","Lip sync","Bring a photo to life",lambda:open_lipsync_window())

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

def refresh():
    for name,port in SERVICES.items():
        status_labels[name].config(fg=GREEN if port_open(port) else RED)
    root.after(3000,refresh)
refresh()

# ---------- Image generator window ----------
def open_generator():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("OVRLKD - Create images"); win.configure(bg=BG)
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
    char_var=tk.BooleanVar(value=False)
    cb=tk.Checkbutton(win,text="\U0001f9cd  Character for 3D/rigging (A-pose, full body, front view)",
        variable=char_var,font=sub_f,bg=BG,fg=FG,selectcolor=CARD,activebackground=BG,activeforeground=FG,anchor="w")
    cb.pack(fill="x",padx=24,pady=(2,0))

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
            if char_var.get(): pr=pr+CHAR_SUFFIX
            generate(engine,mf,pr,w,h,hires,set_status,show_image)
            win.after(0,lambda:gen_btn.config(state="normal",text="✨  Generate image"))
        threading.Thread(target=worker,daemon=True).start()

    gen_btn.config(command=do_gen)

# ---------- Image -> 3D window (with file picker) ----------
def open_3d_window():
    from PIL import Image, ImageTk
    if not os.path.exists(os.path.join(cfg.tripo_src_dir, "run.py")):
        _open_cmd(os.path.join(cfg.tripo_dir, "1-Setup-3D-installieren.cmd")); return
    win=tk.Toplevel(root); win.title("OVRLKD - Image to 3D"); win.configure(bg=BG)
    win.geometry("560x640"); win.lift(); win.focus_force()
    make_frameless(win, "Vulture AI — Image to 3D", win.destroy)
    win._img=None
    tk.Label(win,text="\U0001f9ca Image → 3D model",font=title_f,bg=BG,fg=FG).pack(pady=(14,4))
    tk.Label(win,text="Select image → options → create 3D (.obj for Mixamo/Meshy)",font=small_f,bg=BG,fg=SUB).pack(pady=(0,8))

    pathvar=tk.StringVar(value="No image selected yet")
    def pick():
        f=filedialog.askopenfilename(title="Choose image",initialdir=OUTPUT_DIR,
            filetypes=[("Images","*.png *.jpg *.jpeg *.webp"),("All","*.*")])
        if f:
            win._img=f; pathvar.set(os.path.basename(f))
            try:
                im=Image.open(f); im.thumbnail((300,300)); ph=ImageTk.PhotoImage(im)
                prev.config(image=ph,text=""); prev._ref=ph
            except: pass
    tk.Button(win,text="\U0001f4c2  Select image",font=btn_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=pick).pack(fill="x",padx=24,pady=(2,2))
    tk.Label(win,textvariable=pathvar,font=small_f,bg=BG,fg=SUB).pack()
    prev=tk.Label(win,bg=CARD,text="(Preview)",fg=SUB,font=sub_f); prev.pack(padx=24,pady=8,fill="both",expand=True); prev._ref=None

    tex_var=tk.BooleanVar(value=True)
    tk.Checkbutton(win,text="With texture/color (a bit slower)",variable=tex_var,font=sub_f,bg=BG,fg=FG,
        selectcolor=CARD,activebackground=BG,activeforeground=FG).pack(anchor="w",padx=24)
    detrow=tk.Frame(win,bg=BG); detrow.pack(anchor="w",padx=24,pady=(2,0))
    tk.Label(detrow,text="Detail (more polygons = finer, more RAM): ",font=sub_f,bg=BG,fg=SUB).pack(side="left")
    DETAIL={"Standard (256)":256,"High (320)":320,"Maximum (384)":384}
    det_var=tk.StringVar(value="Standard (256)")
    ttk.Combobox(detrow,textvariable=det_var,values=list(DETAIL.keys()),state="readonly",width=15).pack(side="left")

    st=tk.Label(win,text="Tip: character-mode images (A-pose, full body) rig best.",font=small_f,bg=BG,fg=SUB); st.pack(pady=(4,2))
    def set_st(t): win.after(0,lambda:st.config(text=t))

    def do3d():
        if not win._img: set_st("Please select an image first."); return
        go.config(state="disabled",text="Creating 3D... (30-90s)")
        def worker():
            try:
                set_st("Freeing ComfyUI memory for 3D...")
                try: urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/free",data=b'{"unload_models":true,"free_memory":true}',headers={"Content-Type":"application/json"}),timeout=5)
                except: pass
                set_st("Generating 3D model...")
                mcres=DETAIL.get(det_var.get(),256)
                cmd=[cfg.tripo_python,"run.py",win._img,"--output-dir",cfg.tripo_output_dir,"--model-save-format","obj","--mc-resolution",str(mcres),"--pretrained-model-name-or-path",cfg.tripo_model_dir]
                if tex_var.get(): cmd[6:6]=["--bake-texture","--texture-resolution","1024"]
                r=subprocess.run(cmd,cwd=cfg.tripo_src_dir,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
                out=os.path.join(cfg.tripo_output_dir, "0", "mesh.obj")
                if os.path.exists(out):
                    set_st("DONE! mesh.obj created. Opening folder.")
                    os.startfile(os.path.join(cfg.tripo_output_dir, "0"))
                else:
                    set_st("3D creation error (image may be unsuitable).")
            except Exception as e: set_st(f"Error: {e}")
            win.after(0,lambda:go.config(state="normal",text="\U0001f9ca  Create 3D model"))
        threading.Thread(target=worker,daemon=True).start()

    go=tk.Button(win,text="\U0001f9ca  Create 3D model",font=btn_f,bg=ACCENT,fg="#ffffff",relief="flat",cursor="hand2",command=do3d,activebackground=ACCENT_DK,activeforeground="#ffffff")
    go.pack(fill="x",padx=24,pady=(4,4))
    tk.Button(win,text="\U0001f4c1 Open 3D folder",font=small_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",
        command=lambda:os.startfile(cfg.tripo_output_dir) if os.path.exists(cfg.tripo_output_dir) else None).pack(pady=(0,10))

# ---------- Face swap window ----------
def open_faceswap_window():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("OVRLKD - Face swap"); win.configure(bg=BG)
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
    win=tk.Toplevel(root); win.title("OVRLKD - Lip sync"); win.configure(bg=BG)
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

root.mainloop()
