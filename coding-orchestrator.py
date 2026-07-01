# OVRLKD Auto-Splitter fuer den Coding-Agenten.
# EIN grosser Prompt rein -> Planer-Modell zerlegt in kleine Schritte ->
# Aider arbeitet sie automatisch nacheinander ab (jeder Schritt klein = kein Token-Crash,
# keine weggekuerzten Inhalte). Kein Mini-Schnippsel-Tippen noetig.
#
# Aufruf: python coding-orchestrator.py "<projektordner>" "<aufgabe>" [coder-modell] [planer-modell]
import sys, os, json, subprocess, urllib.request, re

OLLAMA = "http://127.0.0.1:11434"
AIDER_PY = r"D:\ai-coder\venv\Scripts\python.exe"
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
    # Wenn der Planer kein gueltiges JSON liefert: simpler Datei-weiser Notfall-Plan
    # (immer noch klein-schrittig = lieber das als ein Mammut-Edit).
    steps=[]
    for f in files:
        steps.append({"title":f"Aufgabe auf {f} anwenden","files":[f],
            "instruction":f"Wende folgende Aufgabe NUR auf {f} an, soweit fuer diese Datei sinnvoll. "
                          f"Aendere chirurgisch, behalte alle bestehenden Inhalte. Aufgabe: {task}"})
    return steps

def plan(planner, task, files):
    system = ("/no_think Du bist ein Senior-Software-Architekt. Zerlege eine Coding-Aufgabe in eine GEORDNETE Liste "
        "KLEINER, in sich abgeschlossener Schritte. REGELN: jeder Schritt betrifft moeglichst WENIGE Dateien "
        "(idealerweise EINE). Jeder Schritt ist EINE fokussierte Aenderung. Maximal 3-8 Schritte. "
        "Aenderungen sind CHIRURGISCH/ergaenzend - niemals eine ganze Datei von Grund auf neu schreiben, "
        "niemals bestehende Inhalte loeschen ausser es ist ausdruecklich gefordert. "
        "Antworte AUSSCHLIESSLICH mit einem JSON-Array, kein Fliesstext, kein Markdown, keine Erklaerung: "
        '[{"title":"kurz","files":["styles.css"],"instruction":"praezise Anweisung; erwaehne dass der Rest unangetastet bleibt"}]')
    prompt = f"Projekt-Dateien: {files}\n\nAufgabe:\n{task}\n\nGib jetzt NUR das JSON-Array aus."
    try:
        raw = ollama_gen(planner, system, prompt)
    except Exception as e:
        print(f"  (Planer nicht erreichbar: {e} - nutze Notfall-Plan)"); return _fallback_plan(task, files)
    raw = raw.strip()
    raw = re.sub(r"^```[a-zA-Z]*\s*","",raw); raw = re.sub(r"```$","",raw).strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m: raw = m.group(0)
    try:
        steps = json.loads(raw)
        if not isinstance(steps,list) or not steps: raise ValueError("leer")
    except Exception:
        print("  (Planer-Antwort war kein gueltiges JSON - nutze Notfall-Plan)")
        return _fallback_plan(task, files)
    clean=[]
    for s in steps:
        if not isinstance(s,dict): continue
        sf=[f for f in s.get("files",[]) if f in files]
        instr=s.get("instruction","") or s.get("title","")
        if not instr: continue
        clean.append({"title":s.get("title","Schritt"),"files":sf or files,"instruction":instr})
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
        print('Aufruf: coding-orchestrator.py "<ordner>" "<aufgabe>" [coder] [planer]'); return
    proj=sys.argv[1]; task=sys.argv[2]
    coder=sys.argv[3] if len(sys.argv)>3 else "ollama_chat/qwen2.5-coder:7b"
    planner=sys.argv[4] if len(sys.argv)>4 else "qwen2.5-coder:7b"
    if not os.path.isdir(proj): print("Ordner nicht gefunden:",proj); return
    files=list_files(proj)
    if not files: print("Keine Code-Dateien gefunden."); return
    print(f"[Auto-Splitter] Projekt: {proj}")
    print(f"[Auto-Splitter] {len(files)} Dateien: {files}")
    print(f"[Planer: {planner}] zerlege Aufgabe in Schritte...")
    try:
        steps=plan(planner, task, files)
    except Exception as e:
        print("Planer-Fehler (kein gueltiges JSON):",e); return
    if not steps: print("Planer lieferte keine Schritte."); return
    print(f"\n[Plan] {len(steps)} Schritte:")
    for i,s in enumerate(steps,1): print(f"  {i}. {s['title']}  -> {s['files']}")
    print(f"\n[Coder: {coder}] arbeite Schritte ab...\n")
    ok=0
    for i,s in enumerate(steps,1):
        print(f"=== Schritt {i}/{len(steps)}: {s['title']}  ({s['files']}) ===")
        rc,applied,limit=run_step(coder, proj, s['files'], s['instruction'])
        status = "OK (Edit angewendet)" if applied else ("TOKEN-LIMIT!" if limit else f"kein Edit (rc={rc})")
        if applied: ok+=1
        print(f"   -> {status}\n")
    print(f"[Fertig] {ok}/{len(steps)} Schritte angewendet.")

if __name__=="__main__":
    main()
