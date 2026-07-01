# Overlkd auto-splitter for the coding agent.
# ONE big prompt in -> the planner model breaks it into small steps ->
# Aider works through them one after another automatically (each step small = no token crash,
# no truncated content). No tiny-snippet typing needed.
#
# Usage: python coding-orchestrator.py "<project folder>" "<task>" [coder-model] [planner-model]
import sys, os, json, subprocess, urllib.request, re

# Portable paths/ports from the shared config (auto-detect + config.json).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find the vulture pkg
from vulture.config import get_config
cfg = get_config()

OLLAMA = cfg.ollama_api                 # was "http://127.0.0.1:11434"
AIDER_PY = cfg.aider_python             # was r"D:\ai-coder\venv\Scripts\python.exe"
CODE_EXTS = (".html",".htm",".css",".js",".ts",".jsx",".tsx",".vue",".py",".json",".md",".svelte")

def ollama_gen(model, system, prompt, num_ctx=8192, num_predict=1600):
    body = json.dumps({"model":model,"system":system,"prompt":prompt,"stream":False,
        "keep_alive":"5m","options":{"temperature":0.2,"num_ctx":num_ctx,"num_predict":num_predict}}).encode()
    req = urllib.request.Request(OLLAMA+"/api/generate",data=body,headers={"Content-Type":"application/json"})
    out = json.loads(urllib.request.urlopen(req,timeout=600).read()).get("response","")
    return re.sub(r"<think>.*?</think>","",out,flags=re.DOTALL).strip()

def list_files(proj):
    files=[]
    for root,dirs,fs in os.walk(proj):
        dirs[:] = [d for d in dirs if d not in (".git","node_modules","__pycache__",".venv","venv")]
        for f in fs:
            if f.startswith(".aider") or f.endswith(("_bak",".bak")): continue
            if f.lower().endswith(CODE_EXTS):
                files.append(os.path.relpath(os.path.join(root,f),proj).replace("\\","/"))
    return files

def _fallback_plan(task, files):
    # If the planner returns no valid JSON: a simple file-by-file emergency plan
    # (still small-step = better this than one mammoth edit).
    steps=[]
    for f in files:
        steps.append({"title":f"Apply task to {f}","files":[f],
            "instruction":f"Apply the following task ONLY to {f}, as far as it makes sense for this file. "
                          f"Change surgically, keep all existing content. Task: {task}"})
    return steps

def plan(planner, task, files):
    system = ("/no_think You are a senior software architect. Break a coding task into an ORDERED list "
        "of SMALL, self-contained steps. RULES: each step touches as FEW files as possible "
        "(ideally ONE). Each step is ONE focused change. At most 3-8 steps. "
        "Changes are SURGICAL/additive - never rewrite an entire file from scratch, "
        "never delete existing content unless it is explicitly requested. "
        "Reply EXCLUSIVELY with a JSON array, no prose, no markdown, no explanation: "
        '[{"title":"short","files":["styles.css"],"instruction":"precise instruction; mention that the rest stays untouched"}]')
    prompt = f"Project files: {files}\n\nTask:\n{task}\n\nNow output ONLY the JSON array."
    try:
        raw = ollama_gen(planner, system, prompt)
    except Exception as e:
        print(f"  (planner unreachable: {e} - using the emergency plan)"); return _fallback_plan(task, files)
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\s*","",raw); raw = re.sub(r"```$","",raw).strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m: raw = m.group(0)
    try:
        steps = json.loads(raw)
        if not isinstance(steps,list) or not steps: raise ValueError("empty")
    except Exception:
        print("  (planner reply was not valid JSON - using the emergency plan)")
        return _fallback_plan(task, files)
    clean=[]
    for s in steps:
        if not isinstance(s,dict): continue
        sf=[f for f in s.get("files",[]) if f in files]
        instr=s.get("instruction","") or s.get("title","")
        if not instr: continue
        clean.append({"title":s.get("title","Step"),"files":sf or files,"instruction":instr})
    return clean or _fallback_plan(task, files)

def run_step(coder, proj, files, instruction):
    args=[AIDER_PY,"-m","aider","--model",coder,"--no-git","--yes-always","--no-auto-commits",
          "--message",instruction]+files
    env=dict(os.environ, OLLAMA_API_BASE=OLLAMA)
    try:
        r=subprocess.run(args,cwd=proj,capture_output=True,text=True,env=env,timeout=1200)
        applied = "Applied edit" in (r.stdout or "")
        limit = "token limit" in (r.stdout or "").lower()
        return r.returncode, applied, limit
    except subprocess.TimeoutExpired:
        return -1, False, False

def main():
    if len(sys.argv)<3:
        print('Usage: coding-orchestrator.py "<folder>" "<task>" [coder] [planner]'); return
    proj=sys.argv[1]; task=sys.argv[2]
    coder=sys.argv[3] if len(sys.argv)>3 else "ollama_chat/qwen2.5-coder:7b"
    planner=sys.argv[4] if len(sys.argv)>4 else "qwen2.5-coder:7b"
    if not os.path.isdir(proj): print("Folder not found:",proj); return
    files=list_files(proj)
    if not files: print("No code files found."); return
    print(f"[Auto-splitter] Project: {proj}")
    print(f"[Auto-splitter] {len(files)} files: {files}")
    print(f"[Planner: {planner}] breaking the task into steps...")
    try:
        steps=plan(planner, task, files)
    except Exception as e:
        print("Planner error (no valid JSON):",e); return
    if not steps: print("Planner returned no steps."); return
    print(f"\n[Plan] {len(steps)} steps:")
    for i,s in enumerate(steps,1): print(f"  {i}. {s['title']}  -> {s['files']}")
    print(f"\n[Coder: {coder}] working through the steps...\n")
    ok=0
    for i,s in enumerate(steps,1):
        print(f"=== Step {i}/{len(steps)}: {s['title']}  ({s['files']}) ===")
        rc,applied,limit=run_step(coder, proj, s['files'], s['instruction'])
        status = "OK (edit applied)" if applied else ("TOKEN LIMIT!" if limit else f"no edit (rc={rc})")
        if applied: ok+=1
        print(f"   -> {status}\n")
    print(f"[Done] {ok}/{len(steps)} steps applied.")

if __name__=="__main__":
    main()
