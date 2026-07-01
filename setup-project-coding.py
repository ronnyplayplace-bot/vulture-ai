# Richtet pro Projekt den Auto-Test/Lint-Repair-Loop fuer Aider ein (groesster Qualitaetshebel
# fuer lokale Modelle: generate -> test -> Fehler zurueck -> Modell repariert sich selbst).
# Schreibt eine projektlokale .aider.conf.yml mit passendem Test-/Lint-Befehl je Sprache.
# Ueberschreibt NICHT eine bestehende Projekt-Config (nur anlegen wenn nicht vorhanden).
import os, sys, glob

def detect(proj):
    py = os.path.exists(os.path.join(proj,"pyproject.toml")) or os.path.exists(os.path.join(proj,"requirements.txt")) \
         or glob.glob(os.path.join(proj,"*.py")) or glob.glob(os.path.join(proj,"**","*.py"),recursive=True)
    node = os.path.exists(os.path.join(proj,"package.json"))
    has_pytests = bool(glob.glob(os.path.join(proj,"**","test_*.py"),recursive=True)
                       or glob.glob(os.path.join(proj,"**","*_test.py"),recursive=True)
                       or os.path.isdir(os.path.join(proj,"tests")))
    test_cmd=None; lint_cmd=None
    if py:
        lint_cmd="ruff check --fix"            # nur aktiv wenn ruff installiert (Aider faengt Fehlen ab)
        if has_pytests: test_cmd="python -m pytest -q"
    elif node:
        lint_cmd="npx eslint . --fix"
        # nur Test-Loop wenn ein test-Script existiert
        try:
            import json
            with open(os.path.join(proj,"package.json"),encoding="utf-8") as f:
                if "test" in (json.load(f).get("scripts",{})): test_cmd="npm test --silent"
        except Exception: pass
    return test_cmd, lint_cmd

def main():
    if len(sys.argv)<2: return
    proj=sys.argv[1]
    override=sys.argv[2] if len(sys.argv)>2 and sys.argv[2].strip() else None
    conf=os.path.join(proj,".aider.conf.yml")
    if os.path.exists(conf):
        print("Projekt-Config existiert schon - unangetastet gelassen.")
        return
    test_cmd, lint_cmd = detect(proj)
    if override: test_cmd=override
    lines=["# Auto-generiert von OVRLKD (setup-project-coding.py) - Auto-Test/Repair-Loop","auto-lint: true"]
    if lint_cmd: lines.append(f'lint-cmd: "{lint_cmd}"')
    if test_cmd:
        lines += ["auto-test: true", f'test-cmd: "{test_cmd}"']
    with open(conf,"w",encoding="utf-8") as f:
        f.write("\n".join(lines)+"\n")
    if test_cmd:
        print(f"Auto-Test-Loop AKTIV: '{test_cmd}'  (+ Lint: {lint_cmd or 'Aider-intern'})")
    else:
        print(f"Auto-Lint aktiv ({lint_cmd or 'Aider-intern'}). Keine Tests erkannt -> kein Test-Loop (kann man spaeter in .aider.conf.yml ergaenzen).")

if __name__=="__main__":
    main()
