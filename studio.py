# -*- coding: utf-8 -*-
"""OVRLKD Studio KI - Ein Fenster fuer alles, inkl. einfacher Bild-Generator."""
import tkinter as tk
from tkinter import font as tkfont, ttk, messagebox, filedialog
import subprocess, socket, os, threading, webbrowser, json, urllib.request, time, random, io

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", r"C:\Users\User\AppData\Local")
TOOLS = r"C:\Users\User\ai-memory-tools"
COMFY_PY = r"D:\comfyui\venv\Scripts\python.exe"
COMFY_API = "http://127.0.0.1:8188"
OUTPUT_DIR = r"D:\comfyui\output"

BG="#0f1117"; CARD="#1a1d27"; ACCENT="#ff6b35"; FG="#e8e8ed"; SUB="#8a8f9c"; GREEN="#3ddc84"; RED="#ff4d4d"

SERVICES = {"Ollama":11434, "Chat/Bilder (WebUI)":8080, "ComfyUI/FLUX":8188, "Code-RAG":8001, "VPS-Tunnel":8000}

NEG = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, worst quality, low quality, jpeg artifacts, signature, watermark, blurry, ugly, deformed, mutated"

# Modell -> (engine, datei)  -- FLUX ist Standard (beste Qualitaet)
MODELS = {
    "FLUX  (beste Qualitaet)":       ("flux", "flux1-schnell-Q4_K_S.gguf"),
    "DreamShaper  (schnell/Entwurf)":("sd15", "DreamShaper_v8.safetensors"),
    "Realistic Vision  (Foto schnell)":("sd15","RealisticVision_v6.safetensors"),
    "ToonYou  (Cartoon schnell)":    ("sd15", "ToonYou_v6.safetensors"),
}
# Zusatz fuer Charakter-Modus (3D/Rigging): A-Pose, ganzer Koerper, gerade
CHAR_SUFFIX = (", full body character, standing straight in A-pose, arms slightly "
    "away from body, front view, symmetrical, neutral pose, full figure from head to toe, "
    "character reference sheet, plain solid grey background, even lighting, T-pose")
# (Basis-Aufloesung, Hi-Res-Faktor) -> Endergebnis ist Basis * Faktor
SIZES = {
    "Quadrat HD (1024x1024)":   (512,512,2.0),
    "Hochkant HD (1024x1536)":  (512,768,2.0),
    "Quer HD (1536x1024)":      (768,512,2.0),
    "Quadrat schnell (512)":    (512,512,1.0),
}

def port_open(p):
    s=socket.socket(socket.AF_INET,socket.SOCK_STREAM); s.settimeout(0.3)
    try: return s.connect_ex(("127.0.0.1",p))==0
    finally: s.close()

def run_hidden(cmd): subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
def run_visible(cmd): subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)

def ensure_comfy():
    if not port_open(8188):
        run_hidden(f'cd /d "D:\\comfyui\\ComfyUI" && "{COMFY_PY}" main.py --listen 127.0.0.1 --port 8188 --output-directory "{OUTPUT_DIR}" --cuda-device 0 --lowvram')
        return False
    return True

def free_memory():
    # ComfyUI neu starten = RAM wirklich frei (Torch gibt sonst nichts zurueck)
    try: urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/free",data=b'{"unload_models":true,"free_memory":true}',headers={"Content-Type":"application/json"}),timeout=5)
    except: pass
    run_hidden('powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8188 -State Listen -EA SilentlyContinue | %% { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"')

def start_all(): run_hidden(r'"D:\OVRLKD-Studio\OVRLKD-KI.cmd" silent')
def stop_all():
    run_hidden('taskkill /F /IM open-webui.exe /T')
    run_hidden('powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8188,8080,8001,8000 -State Listen -EA SilentlyContinue | %% { Stop-Process -Id $_.OwningProcess -Force -EA SilentlyContinue }"')

def start_webui_and_open():
    if not port_open(8080): run_hidden(f'"{TOOLS}\\start-webui.cmd"')
    webbrowser.open("http://localhost:8080")
def _open_cmd(path):
    # zuverlaessig ein Konsolenfenster oeffnen (os.startfile startet .cmd im eigenen Fenster)
    try: os.startfile(path)
    except Exception:
        subprocess.Popen(f'start "OVRLKD" "{path}"', shell=True)
def open_coder(): _open_cmd(r"D:\OVRLKD-Studio\KI-Coder.cmd")
def open_status(): _open_cmd(r"D:\OVRLKD-Studio\KI-Status.cmd")
def open_3d():
    if os.path.exists(r"D:\tripo3d\TripoSR\run.py"): _open_cmd(r"D:\tripo3d\Bild-zu-3D.cmd")
    else: _open_cmd(r"D:\tripo3d\1-Setup-3D-installieren.cmd")

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
        # Hi-Res-Fix: 2x Latent-Upscale + zweiter Sampler-Pass (echte Details)
        wf["10"]={"inputs":{"samples":["3",0],"scale_by":hires},"class_type":"LatentUpscaleBy"}
        wf["11"]={"inputs":{"seed":seed,"steps":16,"cfg":7,"sampler_name":"dpmpp_2m","scheduler":"karras","denoise":0.45,"model":["4",0],"positive":["6",0],"negative":["7",0],"latent_image":["10",0]},"class_type":"KSampler"}
        wf["8"]["inputs"]["samples"]=["11",0]
    return wf
def wf_flux(prompt, w, h, seed):
    # Pascal-Optimierung: nutzt t5 Q8-GGUF wenn vorhanden (besser als fp8), sonst fp8-Fallback
    t5gguf=r"D:\comfyui\ComfyUI\models\text_encoders\t5-v1_1-xxl-encoder-Q8_0.gguf"
    if os.path.exists(t5gguf) and os.path.getsize(t5gguf)>1000000:
        clip_node={"inputs":{"clip_name1":"t5-v1_1-xxl-encoder-Q8_0.gguf","clip_name2":"clip_l.safetensors","type":"flux"},"class_type":"DualCLIPLoaderGGUF"}
    else:
        clip_node={"inputs":{"clip_name1":"t5xxl_fp8_e4m3fn.safetensors","clip_name2":"clip_l.safetensors","type":"flux"},"class_type":"DualCLIPLoader"}
    return {
      "6":{"inputs":{"text":prompt,"clip":["11",0]},"class_type":"CLIPTextEncode"},
      "5":{"inputs":{"width":w,"height":h,"batch_size":1},"class_type":"EmptySD3LatentImage"},
      "11":clip_node,
      "10":{"inputs":{"vae_name":"flux_ae.safetensors"},"class_type":"VAELoader"},
      "12":{"inputs":{"unet_name":"flux1-schnell-Q4_K_S.gguf"},"class_type":"UnetLoaderGGUF"},
      "13":{"inputs":{"noise":["25",0],"guider":["22",0],"sampler":["16",0],"sigmas":["17",0],"latent_image":["5",0]},"class_type":"SamplerCustomAdvanced"},
      "22":{"inputs":{"model":["12",0],"conditioning":["6",0]},"class_type":"BasicGuider"},
      "16":{"inputs":{"sampler_name":"euler"},"class_type":"KSamplerSelect"},
      "17":{"inputs":{"scheduler":"simple","steps":4,"denoise":1.0,"model":["12",0]},"class_type":"BasicScheduler"},
      "25":{"inputs":{"noise_seed":seed},"class_type":"RandomNoise"},
      "8":{"inputs":{"samples":["13",0],"vae":["10",0]},"class_type":"VAEDecode"},
      "9":{"inputs":{"filename_prefix":"studio_flux","images":["8",0]},"class_type":"SaveImage"},
    }

def wf_img2img(infile, prompt, ckpt, denoise, seed):
    # Bild -> Bild (Variation/Umgestaltung) - native SD1.5 Nodes, laeuft auf 6GB
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
        if not src_path or not os.path.exists(src_path): on_status("Kein Quellbild."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(8188): break
            time.sleep(2)
        inp=r"D:\comfyui\ComfyUI\input"; os.makedirs(inp,exist_ok=True)
        fn="to_img2img.png"; shutil.copy(src_path, os.path.join(inp,fn))
        seed=random.randint(0,2**31)
        wf=wf_img2img(fn, prompt or "high quality, detailed", "RealisticVision_v6.safetensors", denoise, seed)
        path=comfy_run(wf, on_status, "Bild→Bild")
        if path: on_status("Bild→Bild fertig!"); on_image(path)
        else: on_status("Bild→Bild fehlgeschlagen.")
    except Exception as e:
        on_status(f"Bild→Bild Fehler: {e}")

def wf_upscale(infile, scale, ckpt, seed):
    # 4x-UltraSharp + Ultimate SD Upscale (SD1.5 refine, tiled) -> echtes 4K-Detail auf 6GB
    return {
      "1":{"inputs":{"image":infile,"upload":"image"},"class_type":"LoadImage"},
      "2":{"inputs":{"ckpt_name":ckpt},"class_type":"CheckpointLoaderSimple"},
      "3":{"inputs":{"text":"high quality, sharp focus, highly detailed, intricate detail, 8k","clip":["2",1]},"class_type":"CLIPTextEncode"},
      "4":{"inputs":{"text":"blurry, low quality, jpeg artifacts, oversharpened, deformed","clip":["2",1]},"class_type":"CLIPTextEncode"},
      "5":{"inputs":{"model_name":"4x-UltraSharp.pth"},"class_type":"UpscaleModelLoader"},
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
            on_status("Kein Bild zum Hochskalieren."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(8188): break
            time.sleep(2)
        # ComfyUI laedt LoadImage aus input/ -> Bild dorthin kopieren
        inp=r"D:\comfyui\ComfyUI\input"; os.makedirs(inp,exist_ok=True)
        fn="to_upscale.png"; shutil.copy(src_path, os.path.join(inp,fn))
        seed=random.randint(0,2**31)
        wf=wf_upscale(fn, scale, "RealisticVision_v6.safetensors", seed)
        path=comfy_run(wf, on_status, f"Skaliere {int(scale)}x hoch")
        if path: on_status("Hochskaliert fertig!"); on_image(path)
        else: on_status("Laeuft evtl. noch in ComfyUI - schau im Bilder-Ordner (kann auf 6GB lange dauern).")
    except Exception as e:
        on_status(f"Upscale-Fehler: {e}")

def wf_faceswap(target_file, source_file, restore_model="codeformer.pth", visibility=1.0):
    # ReActor Face-Swap: Gesicht aus source_file -> auf target_file. Laeuft offline (inswapper_128 + buffalo_l).
    return {
      "1":{"inputs":{"image":target_file,"upload":"image"},"class_type":"LoadImage"},
      "2":{"inputs":{"image":source_file,"upload":"image"},"class_type":"LoadImage"},
      "3":{"inputs":{
            "enabled":True,"input_image":["1",0],"source_image":["2",0],
            "swap_model":"inswapper_128.onnx","facedetection":"retinaface_resnet50",
            "face_restore_model":restore_model,"face_restore_visibility":visibility,"codeformer_weight":0.5,
            "detect_gender_input":"no","detect_gender_source":"no",
            "input_faces_index":"0","source_faces_index":"0","console_log_level":1},
          "class_type":"ReActorFaceSwap"},
      "9":{"inputs":{"filename_prefix":"faceswap","images":["3",0]},"class_type":"SaveImage"},
    }

# Glaettungs-Stufe -> (CodeFormer-Modell, Sichtbarkeit)
SWAP_RESTORE = {"none":("none",0.0), "light":("codeformer.pth",0.5), "strong":("codeformer.pth",1.0)}

def run_faceswap(target_path, source_path, restore_key, on_status, on_image):
    import shutil
    try:
        if not source_path or not os.path.exists(source_path): on_status("Kein Gesicht-Bild gewaehlt."); return
        if not target_path or not os.path.exists(target_path): on_status("Kein Ziel-Bild gewaehlt."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(8188): break
            time.sleep(2)
        inp=r"D:\comfyui\ComfyUI\input"; os.makedirs(inp,exist_ok=True)
        te=os.path.splitext(target_path)[1].lower() or ".png"; se=os.path.splitext(source_path)[1].lower() or ".png"
        tn="swap_target"+te; sn="swap_source"+se
        shutil.copy(target_path, os.path.join(inp,tn)); shutil.copy(source_path, os.path.join(inp,sn))
        model,vis=SWAP_RESTORE.get(restore_key,("codeformer.pth",1.0))
        wf=wf_faceswap(tn, sn, model, vis)
        path=comfy_run(wf, on_status, "Gesicht tauschen")
        if path: on_status("Gesicht getauscht!"); on_image(path)
        else: on_status("Laeuft evtl. noch in ComfyUI - schau im Bilder-Ordner.")
    except Exception as e:
        on_status(f"Face-Swap Fehler: {e}")

def wf_lipsync(source_file, driving_file, expressiveness=1.0):
    # LivePortrait: Mimik/Lippen aus driving_file (Video) -> auf source_file (Foto). Ton wird durchgeschleift.
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

def comfy_run_video(wf, on_status, label="Lippen-Sync"):
    # wie comfy_run, aber holt am Ende eine Video-Datei (gifs/videos) aus der History
    cid=str(random.randint(1,2**31))
    try:
        pid=json.loads(urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/prompt",
            data=json.dumps({"prompt":wf,"client_id":cid}).encode(),headers={"Content-Type":"application/json"}),timeout=30).read())["prompt_id"]
    except urllib.error.HTTPError as e:
        on_status("Fehler beim Senden: "+e.read().decode()[:200]); return None
    on_status(f"{label} laeuft... (auf 1060 langsam)")
    t0=time.time()
    while time.time()-t0<1800:
        time.sleep(4)
        try:
            h=json.loads(urllib.request.urlopen(f"{COMFY_API}/history/{pid}",timeout=8).read())
        except: continue
        if pid not in h: continue
        st=h[pid].get("status",{})
        if st.get("status_str")=="error": on_status("Fehler in der Verarbeitung (Log pruefen)."); return None
        if st.get("completed") or st.get("status_str")=="success":
            for n,o in h[pid].get("outputs",{}).items():
                for g in o.get("gifs",[])+o.get("videos",[]):
                    return os.path.join(OUTPUT_DIR, g.get("filename"))
            return None
    return None

def run_lipsync(source_path, driving_path, expressiveness, on_status, on_done):
    import shutil
    try:
        if not source_path or not os.path.exists(source_path): on_status("Kein Foto gewaehlt."); return
        if not driving_path or not os.path.exists(driving_path): on_status("Kein Treiber-Video gewaehlt."); return
        ensure_comfy()
        for _ in range(60):
            if port_open(8188): break
            time.sleep(2)
        inp=r"D:\comfyui\ComfyUI\input"; os.makedirs(inp,exist_ok=True)
        se=os.path.splitext(source_path)[1].lower() or ".png"
        sn="lp_src"+se; dn="lp_drive.mp4"
        shutil.copy(source_path, os.path.join(inp,sn)); shutil.copy(driving_path, os.path.join(inp,dn))
        wf=wf_lipsync(sn, dn, expressiveness)
        path=comfy_run_video(wf, on_status, "Lippen-Sync")
        if path: on_status("Lippen-Sync fertig!"); on_done(path)
        else: on_status("Laeuft evtl. noch in ComfyUI - schau im Bilder-Ordner.")
    except Exception as e:
        on_status(f"Lip-Sync Fehler: {e}")

def enhance_prompt(user_text):
    # Lokale KI (qwen) macht aus lockerem/deutschem Text einen guten englischen FLUX-Prompt
    sys=("You are an expert text-to-image prompt engineer for FLUX. Convert the user's request "
         "(any language, may be casual) into ONE concise vivid ENGLISH image description. "
         "Describe ONLY what should be visible: subject, setting, style, lighting, mood, details. "
         "No instructions like 'create/make', no aspect ratio, no quotes, no explanation, no thinking. "
         "Output ONLY the final prompt as a single line.")
    body=json.dumps({"model":"qwen2.5-coder:7b","prompt":user_text,"system":sys,"stream":False,
                     "keep_alive":0,  # Modell sofort aus VRAM entladen -> Platz fuer FLUX (6GB!)
                     "options":{"temperature":0.6,"num_predict":300}}).encode()
    req=urllib.request.Request("http://127.0.0.1:11434/api/generate",data=body,headers={"Content-Type":"application/json"})
    out=json.loads(urllib.request.urlopen(req,timeout=150).read()).get("response","")
    import re as _re
    out=_re.sub(r"<think>.*?</think>","",out,flags=_re.DOTALL).strip().strip('"').strip()
    return out

def comfy_run(wf, on_status, label="Generiere"):
    # Sendet Workflow + zeigt LIVE-Prozent via Websocket, gibt Bildpfad zurueck
    import websocket as _ws
    cid=str(random.randint(1,2**31))
    pid=json.loads(urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/prompt",
        data=json.dumps({"prompt":wf,"client_id":cid}).encode(),headers={"Content-Type":"application/json"}),timeout=30).read())["prompt_id"]
    try:
        ws=_ws.WebSocket(); ws.connect(f"ws://127.0.0.1:8188/ws?clientId={cid}",timeout=10); ws.settimeout(5)
    except Exception:
        ws=None
    done=False; t0=time.time()
    while not done:
        if time.time()-t0>2400: break  # 40min Limit (Upscale auf 6GB mit vielen Kacheln dauert)
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
        # Fallback: History pruefen
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
        on_status("Starte ComfyUI..." if not port_open(8188) else "Sende an KI...")
        if not ensure_comfy():
            for _ in range(60):
                if port_open(8188): break
                time.sleep(2)
            time.sleep(3)
        # FLUX-Dateien da?
        if engine=="flux":
            need=[r"D:\comfyui\ComfyUI\models\unet\flux1-schnell-Q4_K_S.gguf",
                  r"D:\comfyui\ComfyUI\models\text_encoders\t5xxl_fp8_e4m3fn.safetensors",
                  r"D:\comfyui\ComfyUI\models\text_encoders\clip_l.safetensors",
                  r"D:\comfyui\ComfyUI\models\vae\flux_ae.safetensors"]
            if not all(os.path.exists(p) and os.path.getsize(p)>1000000 for p in need):
                on_status("FLUX laedt noch herunter - bitte spaeter."); return
        seed=random.randint(0,2**31)
        wf = wf_flux(prompt,w,h,seed) if engine=="flux" else wf_sd15(model_file,prompt,w,h,seed,hires)
        lbl="Generiere FLUX" if engine=="flux" else "Generiere"
        path=comfy_run(wf, on_status, lbl)
        if path: on_status("Fertig!"); on_image(path)
        else: on_status("Timeout - laeuft evtl. noch, schau im Bilder-Ordner.")
    except Exception as e:
        on_status(f"Fehler: {e}")

# ---------------- GUI ----------------
root=tk.Tk(); root.title("OVRLKD Studio KI"); root.configure(bg=BG)
root.geometry("900x540+140+80"); root.minsize(820,500); root.resizable(True,True)
def _front():
    root.deiconify(); root.lift(); root.attributes("-topmost",True)
    root.after(800,lambda:root.attributes("-topmost",False)); root.focus_force()
root.after(100,_front)

title_f=tkfont.Font(family="Segoe UI",size=20,weight="bold")
btn_f=tkfont.Font(family="Segoe UI",size=13,weight="bold")
sub_f=tkfont.Font(family="Segoe UI",size=9); small_f=tkfont.Font(family="Segoe UI",size=9)

# ---- Kopfzeile ----
head=tk.Frame(root,bg=BG); head.pack(fill="x",padx=24,pady=(16,6))
tk.Label(head,text="OVRLKD STUDIO KI",font=title_f,bg=BG,fg=FG).pack(side="left")
tk.Label(head,text="  dein KI-Studio",font=sub_f,bg=BG,fg=SUB).pack(side="left",pady=(10,0))

# ---- Koerper: links Aktionen (Raster), rechts Status ----
body=tk.Frame(root,bg=BG); body.pack(fill="both",expand=True,padx=20,pady=(4,16))
left=tk.Frame(body,bg=BG); left.pack(side="left",fill="both",expand=True)
right=tk.Frame(body,bg=BG,width=210); right.pack(side="right",fill="y",padx=(16,0)); right.pack_propagate(False)

def _hover(fr,on,base):
    c="#252a36" if on else base
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

# Start ueber volle Breite
make_card(left,0,0,"▶","ALLES STARTEN","Dienste hochfahren",start_all,base=ACCENT,fg="#1a0e08").grid(columnspan=2,sticky="nsew")
make_card(left,1,0,"\U0001f3a8","Bilder erstellen","Text rein, Bild raus",lambda:open_generator())
make_card(left,1,1,"\U0001f4ac","Chat","Lokale KI-Modelle",start_webui_and_open)
make_card(left,2,0,"\U0001f4bb","Coding-Agent","Aider (Terminal)",open_coder)
make_card(left,2,1,"\U0001f9ca","Bild → 3D","Foto -> 3D-Modell",lambda:open_3d_window())
make_card(left,3,0,"\U0001f3c3","Riggen/Animieren","Mixamo (Browser)",lambda:webbrowser.open("https://www.mixamo.com"))
make_card(left,3,1,"\U0001f4ca","Status","RAM / VRAM / GPU",open_status)
make_card(left,4,0,"\U0001f3ad","Gesicht tauschen","Face-Swap (Foto)",lambda:open_faceswap_window())
make_card(left,4,1,"\U0001f444","Lippen-Sync","Foto zum Leben erwecken",lambda:open_lipsync_window())

# ---- Rechte Spalte: Dienste-Status + Speicher/Stop ----
tk.Label(right,text="DIENSTE",font=small_f,bg=BG,fg=SUB).pack(anchor="w",pady=(2,4))
status_labels={}
for name in SERVICES:
    row=tk.Frame(right,bg=BG); row.pack(fill="x",pady=1)
    dot=tk.Label(row,text="●",font=small_f,bg=BG,fg=RED); dot.pack(side="left")
    tk.Label(row,text=" "+name,font=small_f,bg=BG,fg=SUB,anchor="w").pack(side="left")
    status_labels[name]=dot

tk.Frame(right,bg=BG,height=12).pack()
free_f=tk.Frame(right,bg="#16241c",cursor="hand2"); free_f.pack(fill="x",pady=4)
tk.Label(free_f,text="\U0001f9f9  Speicher freigeben",font=sub_f,bg="#16241c",fg=GREEN).pack(pady=10)
for w in [free_f]+list(free_f.winfo_children()): w.bind("<Button-1>",lambda e:free_memory())
stop_f=tk.Frame(right,bg="#2a1518",cursor="hand2"); stop_f.pack(fill="x",pady=4)
tk.Label(stop_f,text="⏹  Alles stoppen",font=sub_f,bg="#2a1518",fg=RED).pack(pady=10)
for w in [stop_f]+list(stop_f.winfo_children()): w.bind("<Button-1>",lambda e:stop_all())

def refresh():
    for name,port in SERVICES.items():
        status_labels[name].config(fg=GREEN if port_open(port) else RED)
    root.after(3000,refresh)
refresh()

# ---------- Bild-Generator Fenster ----------
def open_generator():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("OVRLKD - Bilder erstellen"); win.configure(bg=BG)
    win.geometry("760x860"); win.minsize(560,640); win.resizable(True,True)
    win.lift(); win.focus_force()
    win._last_path=None; win._pil=None
    tk.Label(win,text="\U0001f3a8 Bilder erstellen",font=title_f,bg=BG,fg=FG).pack(pady=(14,8))

    tk.Label(win,text="Was soll auf dem Bild sein?",font=sub_f,bg=BG,fg=SUB).pack(anchor="w",padx=24)
    prompt_box=tk.Text(win,height=3,font=("Segoe UI",11),bg=CARD,fg=FG,insertbackground=FG,relief="flat",wrap="word")
    prompt_box.pack(fill="x",padx=24,pady=(2,10)); prompt_box.insert("1.0","")

    rowf=tk.Frame(win,bg=BG); rowf.pack(fill="x",padx=24)
    tk.Label(rowf,text="Modell / Stil",font=sub_f,bg=BG,fg=SUB).grid(row=0,column=0,sticky="w")
    tk.Label(rowf,text="Format",font=sub_f,bg=BG,fg=SUB).grid(row=0,column=1,sticky="w",padx=(12,0))
    model_var=tk.StringVar(value=list(MODELS.keys())[0])
    size_var=tk.StringVar(value=list(SIZES.keys())[0])
    style=ttk.Style(); style.theme_use("default")
    style.configure("TCombobox",fieldbackground=CARD,background=CARD,foreground=FG,arrowcolor=FG)
    mcb=ttk.Combobox(rowf,textvariable=model_var,values=list(MODELS.keys()),state="readonly",width=28); mcb.grid(row=1,column=0,sticky="w",pady=4)
    scb=ttk.Combobox(rowf,textvariable=size_var,values=list(SIZES.keys()),state="readonly",width=16); scb.grid(row=1,column=1,sticky="w",padx=(12,0),pady=4)

    enhance_var=tk.BooleanVar(value=True)
    tk.Checkbutton(win,text="✨ Prompt von KI optimieren (deutsch/locker ok → macht englischen FLUX-Prompt)",
        variable=enhance_var,font=sub_f,bg=BG,fg=FG,selectcolor=CARD,activebackground=BG,activeforeground=FG,anchor="w").pack(fill="x",padx=24,pady=(2,0))
    char_var=tk.BooleanVar(value=False)
    cb=tk.Checkbutton(win,text="\U0001f9cd  Charakter für 3D/Rigging (A-Pose, ganzer Körper, von vorn)",
        variable=char_var,font=sub_f,bg=BG,fg=FG,selectcolor=CARD,activebackground=BG,activeforeground=FG,anchor="w")
    cb.pack(fill="x",padx=24,pady=(2,0))

    # Buttons ZUERST (immer sichtbar, oben), dann Bild fuellt den Rest
    gen_btn=tk.Button(win,text="✨  Bild generieren",font=btn_f,bg=ACCENT,fg="#1a0e08",relief="flat",cursor="hand2")
    gen_btn.pack(side="top",fill="x",padx=24,pady=(10,4))
    status_lbl=tk.Label(win,text="Bereit.",font=sub_f,bg=BG,fg=GREEN); status_lbl.pack(side="top",pady=(2,4))

    # Unten: Bild gross oeffnen + Ordner
    botf=tk.Frame(win,bg=BG); botf.pack(side="bottom",fill="x",pady=(4,10))
    def open_full():
        if win._last_path and os.path.exists(win._last_path): os.startfile(win._last_path)
        else: os.startfile(OUTPUT_DIR)
    tk.Button(botf,text="\U0001f50d  Bild gross oeffnen",font=sub_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
              command=open_full).pack(side="left",expand=True,fill="x",padx=(24,6))
    tk.Button(botf,text="\U0001f4c1 Ordner",font=sub_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",
              command=lambda:os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(6,24))
    # Bild->Bild Reihe (Variation/Umgestaltung aus Quellbild + Prompt)
    i2f=tk.Frame(win,bg=BG); i2f.pack(side="bottom",fill="x",pady=(0,2))
    def do_img2img():
        f=filedialog.askopenfilename(title="Quellbild fuer Bild→Bild",initialdir=OUTPUT_DIR,
            filetypes=[("Bilder","*.png *.jpg *.jpeg *.webp"),("Alle","*.*")])
        if not f: return
        p=prompt_box.get("1.0","end").strip() or "high quality, detailed"
        set_status("Bild→Bild laeuft...")
        threading.Thread(target=lambda:run_img2img(f,p,0.55,set_status,show_image),daemon=True).start()
    tk.Button(i2f,text="\U0001f5bc️ Bild→Bild (Quellbild + Prompt umgestalten)",font=sub_f,bg="#2a2418",fg="#ffb86b",
              relief="flat",cursor="hand2",command=do_img2img).pack(fill="x",padx=24)
    # Upscale-Reihe (4x-UltraSharp + Ultimate SD Upscale -> echtes Detail)
    upf=tk.Frame(win,bg=BG); upf.pack(side="bottom",fill="x",pady=(0,2))
    def do_upscale(scale):
        if not getattr(win,"_last_path",None): set_status("Erst ein Bild erzeugen oder laden."); return
        threading.Thread(target=lambda:run_upscale(win._last_path,scale,set_status,show_image),daemon=True).start()
    def load_and_4k():
        from PIL import Image, ImageTk
        f=filedialog.askopenfilename(title="Bild laden zum Hochskalieren",initialdir=OUTPUT_DIR,
            filetypes=[("Bilder","*.png *.jpg *.jpeg *.webp"),("Alle","*.*")])
        if not f: return
        win._last_path=f
        try:
            win._pil=Image.open(f); _rescale()
        except: pass
        set_status("Geladen - skaliere auf 4K...")
        threading.Thread(target=lambda:run_upscale(f,4.0,set_status,show_image),daemon=True).start()
    tk.Button(upf,text="\U0001f53c HD (2x)",font=sub_f,bg="#1d2733",fg=GREEN,relief="flat",cursor="hand2",
              command=lambda:do_upscale(2.0)).pack(side="left",expand=True,fill="x",padx=(24,3))
    tk.Button(upf,text="\U0001f53c 4K (4x)",font=sub_f,bg="#1d2733",fg=GREEN,relief="flat",cursor="hand2",
              command=lambda:do_upscale(4.0)).pack(side="left",expand=True,fill="x",padx=3)
    tk.Button(upf,text="\U0001f4c2 Bild laden→4K",font=sub_f,bg="#1d2733",fg=GREEN,relief="flat",cursor="hand2",
              command=load_and_4k).pack(side="left",expand=True,fill="x",padx=(3,24))

    img_lbl=tk.Label(win,bg=CARD,text="(hier erscheint dein Bild)",fg=SUB,font=sub_f)
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
                set_status("Fertig! Gespeichert in "+os.path.basename(path))
                os.startfile(path)  # oeffnet automatisch im Bildbetrachter
            except Exception as e: set_status(f"Anzeige-Fehler: {e}")
        win.after(0,_do)
    win.bind("<Configure>", lambda e: _rescale() if e.widget is win else None)

    def do_gen():
        p=prompt_box.get("1.0","end").strip()
        if not p: set_status("Bitte erst etwas eintippen."); return
        gen_btn.config(state="disabled",text="Generiere...")
        engine,mf=MODELS[model_var.get()]; w,h,hires=SIZES[size_var.get()]
        def worker():
            pr=p
            if enhance_var.get():
                set_status("KI optimiert deinen Prompt...")
                try:
                    better=enhance_prompt(p)
                    if better: pr=better; set_status("Optimiert: "+pr[:70]+"...")
                except Exception as e: set_status(f"Optimierung uebersprungen ({e}) - nutze Original")
            if char_var.get(): pr=pr+CHAR_SUFFIX
            generate(engine,mf,pr,w,h,hires,set_status,show_image)
            win.after(0,lambda:gen_btn.config(state="normal",text="✨  Bild generieren"))
        threading.Thread(target=worker,daemon=True).start()

    gen_btn.config(command=do_gen)

# ---------- Bild -> 3D Fenster (mit Datei-Auswahl) ----------
def open_3d_window():
    from PIL import Image, ImageTk
    if not os.path.exists(r"D:\tripo3d\TripoSR\run.py"):
        _open_cmd(r"D:\tripo3d\1-Setup-3D-installieren.cmd"); return
    win=tk.Toplevel(root); win.title("OVRLKD - Bild zu 3D"); win.configure(bg=BG)
    win.geometry("560x640"); win.lift(); win.focus_force()
    win._img=None
    tk.Label(win,text="\U0001f9ca Bild → 3D-Modell",font=title_f,bg=BG,fg=FG).pack(pady=(14,4))
    tk.Label(win,text="Bild auswaehlen → Optionen → 3D erstellen (.obj fuer Mixamo/Meshy)",font=small_f,bg=BG,fg=SUB).pack(pady=(0,8))

    pathvar=tk.StringVar(value="Noch kein Bild gewaehlt")
    def pick():
        f=filedialog.askopenfilename(title="Bild waehlen",initialdir=OUTPUT_DIR,
            filetypes=[("Bilder","*.png *.jpg *.jpeg *.webp"),("Alle","*.*")])
        if f:
            win._img=f; pathvar.set(os.path.basename(f))
            try:
                im=Image.open(f); im.thumbnail((300,300)); ph=ImageTk.PhotoImage(im)
                prev.config(image=ph,text=""); prev._ref=ph
            except: pass
    tk.Button(win,text="\U0001f4c2  Bild auswaehlen",font=btn_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=pick).pack(fill="x",padx=24,pady=(2,2))
    tk.Label(win,textvariable=pathvar,font=small_f,bg=BG,fg=SUB).pack()
    prev=tk.Label(win,bg=CARD,text="(Vorschau)",fg=SUB,font=sub_f); prev.pack(padx=24,pady=8,fill="both",expand=True); prev._ref=None

    tex_var=tk.BooleanVar(value=True)
    tk.Checkbutton(win,text="Mit Textur/Farbe (etwas langsamer)",variable=tex_var,font=sub_f,bg=BG,fg=FG,
        selectcolor=CARD,activebackground=BG,activeforeground=FG).pack(anchor="w",padx=24)
    detrow=tk.Frame(win,bg=BG); detrow.pack(anchor="w",padx=24,pady=(2,0))
    tk.Label(detrow,text="Detail (mehr Polygone = feiner, mehr RAM): ",font=sub_f,bg=BG,fg=SUB).pack(side="left")
    DETAIL={"Standard (256)":256,"Hoch (320)":320,"Maximum (384)":384}
    det_var=tk.StringVar(value="Standard (256)")
    ttk.Combobox(detrow,textvariable=det_var,values=list(DETAIL.keys()),state="readonly",width=15).pack(side="left")

    st=tk.Label(win,text="Tipp: Charakter-Modus-Bilder (A-Pose, ganzer Koerper) riggen am besten.",font=small_f,bg=BG,fg=SUB); st.pack(pady=(4,2))
    def set_st(t): win.after(0,lambda:st.config(text=t))

    def do3d():
        if not win._img: set_st("Bitte erst ein Bild auswaehlen."); return
        go.config(state="disabled",text="Erstelle 3D... (30-90s)")
        def worker():
            try:
                set_st("ComfyUI-Speicher wird fuer 3D freigegeben...")
                try: urllib.request.urlopen(urllib.request.Request(f"{COMFY_API}/free",data=b'{"unload_models":true,"free_memory":true}',headers={"Content-Type":"application/json"}),timeout=5)
                except: pass
                set_st("Erzeuge 3D-Modell...")
                mcres=DETAIL.get(det_var.get(),256)
                cmd=[r"D:\tripo3d\venv\Scripts\python.exe","run.py",win._img,"--output-dir",r"D:\tripo3d\output","--model-save-format","obj","--mc-resolution",str(mcres),"--pretrained-model-name-or-path",r"D:\tripo3d\model"]
                if tex_var.get(): cmd[6:6]=["--bake-texture","--texture-resolution","1024"]
                r=subprocess.run(cmd,cwd=r"D:\tripo3d\TripoSR",capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
                out=r"D:\tripo3d\output\0\mesh.obj"
                if os.path.exists(out):
                    set_st("FERTIG! mesh.obj erstellt. Ordner oeffnet sich.")
                    os.startfile(r"D:\tripo3d\output\0")
                else:
                    set_st("Fehler bei der 3D-Erstellung (Bild evtl. ungeeignet).")
            except Exception as e: set_st(f"Fehler: {e}")
            win.after(0,lambda:go.config(state="normal",text="\U0001f9ca  3D-Modell erstellen"))
        threading.Thread(target=worker,daemon=True).start()

    go=tk.Button(win,text="\U0001f9ca  3D-Modell erstellen",font=btn_f,bg=ACCENT,fg="#1a0e08",relief="flat",cursor="hand2",command=do3d)
    go.pack(fill="x",padx=24,pady=(4,4))
    tk.Button(win,text="\U0001f4c1 3D-Ordner oeffnen",font=small_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",
        command=lambda:os.startfile(r"D:\tripo3d\output") if os.path.exists(r"D:\tripo3d\output") else None).pack(pady=(0,10))

# ---------- Gesicht tauschen (Face-Swap) Fenster ----------
def open_faceswap_window():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("OVRLKD - Gesicht tauschen"); win.configure(bg=BG)
    win.geometry("640x760"); win.minsize(560,680); win.lift(); win.focus_force()
    win._src=None; win._tgt=None; win._last=None
    tk.Label(win,text="\U0001f3ad Gesicht tauschen",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="Dein Gesicht (1) kommt auf das Ziel-Bild (2). Laeuft 100% offline.",font=small_f,bg=BG,fg=SUB).pack(pady=(0,8))

    grid=tk.Frame(win,bg=BG); grid.pack(fill="x",padx=24)
    grid.columnconfigure(0,weight=1); grid.columnconfigure(1,weight=1)
    srcvar=tk.StringVar(value="kein Gesicht gewaehlt"); tgtvar=tk.StringVar(value="kein Ziel gewaehlt")
    tk.Label(grid,text="1) DEIN GESICHT",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=0,sticky="w")
    tk.Label(grid,text="2) ZIEL-BILD (Body/Szene)",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=1,sticky="w",padx=(6,0))
    src_prev=tk.Label(grid,bg=CARD,text="(Vorschau)",fg=SUB,font=small_f,height=9); src_prev.grid(row=1,column=0,sticky="nsew",padx=(0,6),pady=4); src_prev._ref=None
    tgt_prev=tk.Label(grid,bg=CARD,text="(Vorschau)",fg=SUB,font=small_f,height=9); tgt_prev.grid(row=1,column=1,sticky="nsew",padx=(6,0),pady=4); tgt_prev._ref=None
    def pick_into(which,prev,var):
        f=filedialog.askopenfilename(title="Bild waehlen",initialdir=os.path.expanduser("~\\Desktop"),
            filetypes=[("Bilder","*.png *.jpg *.jpeg *.webp"),("Alle","*.*")])
        if not f: return
        if which=="src": win._src=f
        else: win._tgt=f
        var.set(os.path.basename(f)[:34])
        try:
            im=Image.open(f); im.thumbnail((250,250)); ph=ImageTk.PhotoImage(im)
            prev.config(image=ph,text=""); prev._ref=ph
        except: pass
    tk.Button(grid,text="\U0001f4c2 Gesicht waehlen",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
        command=lambda:pick_into("src",src_prev,srcvar)).grid(row=2,column=0,sticky="ew",padx=(0,6),pady=2)
    tk.Button(grid,text="\U0001f4c2 Ziel waehlen",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
        command=lambda:pick_into("tgt",tgt_prev,tgtvar)).grid(row=2,column=1,sticky="ew",padx=(6,0),pady=2)
    tk.Label(grid,textvariable=srcvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=0,sticky="w")
    tk.Label(grid,textvariable=tgtvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=1,sticky="w",padx=(6,0))

    optf=tk.Frame(win,bg=BG); optf.pack(fill="x",padx=24,pady=(8,2))
    tk.Label(optf,text="Kanten-Glaettung: ",font=sub_f,bg=BG,fg=SUB).pack(side="left")
    REST={"Stark (empfohlen)":"strong","Leicht":"light","Aus (roh)":"none"}
    rest_var=tk.StringVar(value="Stark (empfohlen)")
    ttk.Combobox(optf,textvariable=rest_var,values=list(REST.keys()),state="readonly",width=18).pack(side="left")

    go=tk.Button(win,text="\U0001f3ad  Gesichter tauschen",font=btn_f,bg=ACCENT,fg="#1a0e08",relief="flat",cursor="hand2")
    go.pack(fill="x",padx=24,pady=(10,4))
    st=tk.Label(win,text="Bereit. Erster Lauf laedt Modelle (~1-3 min auf 6GB).",font=sub_f,bg=BG,fg=GREEN); st.pack(pady=(2,4))
    botf=tk.Frame(win,bg=BG); botf.pack(side="bottom",fill="x",pady=(4,10))
    tk.Button(botf,text="\U0001f50d Gross oeffnen",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",
        command=lambda:os.startfile(win._last) if win._last and os.path.exists(win._last) else os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(24,6))
    tk.Button(botf,text="\U0001f4c1 Ordner",font=small_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",
        command=lambda:os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(6,24))
    res=tk.Label(win,bg=CARD,text="(Ergebnis erscheint hier)",fg=SUB,font=sub_f); res.pack(side="top",padx=24,pady=6,fill="both",expand=True); res._ref=None

    def set_st(t): win.after(0,lambda:st.config(text=t))
    def show(path):
        def _do():
            try:
                win._last=path; im=Image.open(path); im.thumbnail((400,400)); ph=ImageTk.PhotoImage(im)
                res.config(image=ph,text=""); res._ref=ph
                set_st("Fertig! "+os.path.basename(path)); os.startfile(path)
            except Exception as e: set_st(f"Anzeige-Fehler: {e}")
        win.after(0,_do)
    def do_swap():
        if not win._src: set_st("Bitte erst dein Gesicht-Bild waehlen (1)."); return
        if not win._tgt: set_st("Bitte erst ein Ziel-Bild waehlen (2)."); return
        go.config(state="disabled",text="Tausche...")
        key=REST.get(rest_var.get(),"strong")
        def worker():
            run_faceswap(win._tgt,win._src,key,set_st,show)
            win.after(0,lambda:go.config(state="normal",text="\U0001f3ad  Gesichter tauschen"))
        threading.Thread(target=worker,daemon=True).start()
    go.config(command=do_swap)

# ---------- Lippen-Sync (LivePortrait) Fenster ----------
def open_lipsync_window():
    from PIL import Image, ImageTk
    win=tk.Toplevel(root); win.title("OVRLKD - Lippen-Sync"); win.configure(bg=BG)
    win.geometry("640x620"); win.minsize(560,560); win.lift(); win.focus_force()
    win._src=None; win._drv=None; win._last=None
    tk.Label(win,text="\U0001f444 Lippen-Sync",font=title_f,bg=BG,fg=FG).pack(pady=(14,2))
    tk.Label(win,text="Foto (1) wird durch ein Treiber-Video (2) zum Leben erweckt - Mimik, Lippen, Kopf. Ton wird uebernommen.",
             font=small_f,bg=BG,fg=SUB,wraplength=600).pack(pady=(0,8))

    grid=tk.Frame(win,bg=BG); grid.pack(fill="x",padx=24)
    grid.columnconfigure(0,weight=1); grid.columnconfigure(1,weight=1)
    srcvar=tk.StringVar(value="kein Foto"); drvvar=tk.StringVar(value="kein Video")
    tk.Label(grid,text="1) FOTO (Gesicht)",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=0,sticky="w")
    tk.Label(grid,text="2) TREIBER-VIDEO (jemand spricht/bewegt sich)",font=small_f,bg=BG,fg=ACCENT).grid(row=0,column=1,sticky="w",padx=(6,0))
    src_prev=tk.Label(grid,bg=CARD,text="(Vorschau)",fg=SUB,font=small_f,height=8); src_prev.grid(row=1,column=0,sticky="nsew",padx=(0,6),pady=4); src_prev._ref=None
    drv_box=tk.Label(grid,bg=CARD,text="(mp4 / mov / webm)",fg=SUB,font=small_f,height=8); drv_box.grid(row=1,column=1,sticky="nsew",padx=(6,0),pady=4)
    def pick_src():
        f=filedialog.askopenfilename(title="Foto waehlen",initialdir=os.path.expanduser("~\\Desktop"),
            filetypes=[("Bilder","*.png *.jpg *.jpeg *.webp"),("Alle","*.*")])
        if not f: return
        win._src=f; srcvar.set(os.path.basename(f)[:34])
        try:
            im=Image.open(f); im.thumbnail((250,250)); ph=ImageTk.PhotoImage(im); src_prev.config(image=ph,text=""); src_prev._ref=ph
        except: pass
    def pick_drv():
        f=filedialog.askopenfilename(title="Treiber-Video waehlen",initialdir=os.path.expanduser("~\\Desktop"),
            filetypes=[("Videos","*.mp4 *.mov *.webm *.avi *.mkv"),("Alle","*.*")])
        if not f: return
        win._drv=f; drvvar.set(os.path.basename(f)[:34]); drv_box.config(text="\U0001f3ac\n"+os.path.basename(f)[:24])
    tk.Button(grid,text="\U0001f4c2 Foto waehlen",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=pick_src).grid(row=2,column=0,sticky="ew",padx=(0,6),pady=2)
    tk.Button(grid,text="\U0001f4c2 Video waehlen",font=small_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=pick_drv).grid(row=2,column=1,sticky="ew",padx=(6,0),pady=2)
    tk.Label(grid,textvariable=srcvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=0,sticky="w")
    tk.Label(grid,textvariable=drvvar,font=small_f,bg=BG,fg=SUB).grid(row=3,column=1,sticky="w",padx=(6,0))

    optf=tk.Frame(win,bg=BG); optf.pack(fill="x",padx=24,pady=(8,2))
    tk.Label(optf,text="Ausdrucksstaerke: ",font=sub_f,bg=BG,fg=SUB).pack(side="left")
    EXPR={"Natuerlich":1.0,"Dezent":0.7,"Stark":1.4}
    expr_var=tk.StringVar(value="Natuerlich")
    ttk.Combobox(optf,textvariable=expr_var,values=list(EXPR.keys()),state="readonly",width=14).pack(side="left")

    go=tk.Button(win,text="\U0001f444  Foto zum Leben erwecken",font=btn_f,bg=ACCENT,fg="#1a0e08",relief="flat",cursor="hand2")
    go.pack(fill="x",padx=24,pady=(10,4))
    st=tk.Label(win,text="Tipp: Frontales Foto + kurzes Treiber-Video (3-8s) = bestes Ergebnis. Auf 1060 langsam.",font=sub_f,bg=BG,fg=GREEN,wraplength=600); st.pack(pady=(2,4))
    botf=tk.Frame(win,bg=BG); botf.pack(side="bottom",fill="x",pady=(6,12))
    def open_res():
        if win._last and os.path.exists(win._last): os.startfile(win._last)
        else: os.startfile(OUTPUT_DIR)
    tk.Button(botf,text="▶ Video abspielen",font=sub_f,bg=CARD,fg=FG,relief="flat",cursor="hand2",command=open_res).pack(side="left",expand=True,fill="x",padx=(24,6))
    tk.Button(botf,text="\U0001f4c1 Ordner",font=sub_f,bg=CARD,fg=SUB,relief="flat",cursor="hand2",command=lambda:os.startfile(OUTPUT_DIR)).pack(side="left",expand=True,fill="x",padx=(6,24))

    def set_st(t): win.after(0,lambda:st.config(text=t))
    def done(path):
        win._last=path
        set_st("Fertig! "+os.path.basename(path)+" - oeffnet sich...")
        try: os.startfile(path)
        except: pass
    def do_go():
        if not win._src: set_st("Bitte erst ein Foto waehlen (1)."); return
        if not win._drv: set_st("Bitte erst ein Treiber-Video waehlen (2)."); return
        go.config(state="disabled",text="Erwecke... (kann dauern)")
        ex=EXPR.get(expr_var.get(),1.0)
        def worker():
            run_lipsync(win._src,win._drv,ex,set_st,done)
            win.after(0,lambda:go.config(state="normal",text="\U0001f444  Foto zum Leben erwecken"))
        threading.Thread(target=worker,daemon=True).start()
    go.config(command=do_go)

root.mainloop()
