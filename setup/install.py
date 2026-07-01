# -*- coding: utf-8 -*-
"""Vulture AI (Overlkd Studio) -- one-shot, idempotent bootstrap installer.

Goal / acceptance test:
    delete everything -> `git clone` -> `python setup/install.py` -> it runs.

From a fresh clone this rebuilds the *whole* environment, in order:

    1. comfyui  -- clone ComfyUI + create its venv + install cu121 torch + requirements
    2. nodes    -- clone the custom nodes the workflows need + their pip deps,
                   then force  numpy==1.26.4  (insightface/mediapipe need it)
    3. models   -- download only the MISSING model files from their original
                   sources (HuggingFace via huggingface_hub, GitHub via requests)
    4. ollama   -- `ollama pull` the missing LLMs
    5. config   -- write config.json with the resolved paths so studio.py is portable

Everything is idempotent: rerun it any time; present items are skipped.
Nothing here is destructive and nothing is uploaded.

Usage (Windows, from the repo root)::

    python setup/install.py                 # full bootstrap, required items only
    python setup/install.py --all           # also the optional models + nodes
    python setup/install.py --list          # show what exists / is missing, download nothing
    python setup/install.py --steps models  # just (re)download model files
    python setup/install.py --dry-run       # print planned actions only

Heavy third-party deps are optional and imported lazily; only
``huggingface_hub``, ``requests`` and ``tqdm`` are needed, and only for the
download step.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Make the repo root importable so `import vulture.config` works from setup/.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vulture.config import (  # noqa: E402
    Config, load_config, _available_drives, _norm, _rag_base_dir,
)

MANIFEST_PATH = Path(__file__).resolve().parent / "models.manifest.json"
STEP_ORDER = ["comfyui", "nodes", "models", "ollama", "rag", "config"]


# --------------------------------------------------------------------------- #
# Console helpers
# --------------------------------------------------------------------------- #
def banner(text: str) -> None:
    line = "=" * 64
    print(f"\n{line}\n  {text}\n{line}")


def info(msg: str) -> None:
    print(f"  {msg}")


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def skip(msg: str) -> None:
    print(f"  [skip] {msg}")


def warn(msg: str) -> None:
    print(f"  [!]    {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def human_mb(mb: Optional[float]) -> str:
    if not mb:
        return "?"
    mb = float(mb)
    return f"{mb/1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


# --------------------------------------------------------------------------- #
# Subprocess wrapper (streams output so the user sees progress)
# --------------------------------------------------------------------------- #
def run(cmd: List[str], cwd: Optional[str] = None, env_overlay: Optional[Dict[str, str]] = None,
        dry: bool = False, check: bool = True) -> int:
    """Run ``cmd`` inheriting stdio. Returns the exit code."""
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    info(f"$ {printable}" + (f"   (cwd={cwd})" if cwd else ""))
    if dry:
        return 0
    env = os.environ.copy()
    if env_overlay:
        env.update(env_overlay)
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env)
    except FileNotFoundError as exc:
        fail(f"command not found: {cmd[0]} ({exc})")
        return 127
    if check and proc.returncode != 0:
        warn(f"command exited with code {proc.returncode}")
    return proc.returncode


# --------------------------------------------------------------------------- #
# Optional dependency loaders
# --------------------------------------------------------------------------- #
def _ensure_pip_deps(dry: bool = False) -> bool:
    """Make sure huggingface_hub / requests / tqdm are importable.

    Installs them into the *current* interpreter if missing.
    Returns True if all three are available afterwards.
    """
    missing = []
    for mod in ("huggingface_hub", "requests", "tqdm"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if not missing:
        return True
    warn(f"installing downloader deps: {', '.join(missing)}")
    run([sys.executable, "-m", "pip", "install", "--upgrade", *missing], dry=dry)
    for mod in ("huggingface_hub", "requests", "tqdm"):
        try:
            __import__(mod)
        except ImportError:
            fail(f"could not import {mod} after install")
            return False
    return True


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def load_manifest() -> Dict[str, Any]:
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def target_base_dir(cfg: Config, base: str) -> str:
    """Resolve a manifest ``target_base`` token to a real directory."""
    return {
        "comfy_models": cfg.comfy_models_dir,
        "comfy_custom_nodes": cfg.comfy_custom_nodes_dir,
        "comfy_root": cfg.comfy_dir,
        "output": cfg.output_dir,
        "ollama": cfg.ollama_models_dir,
    }.get(base, cfg.comfy_models_dir)


def model_target_path(cfg: Config, entry: Dict[str, Any]) -> str:
    base = target_base_dir(cfg, entry.get("target_base", "comfy_models"))
    return _norm(os.path.join(base, entry["target_relative_path"]))


def is_present(entry: Dict[str, Any], path: str) -> bool:
    """Existence check: file >1MB, or non-empty directory (snapshots/zip extracts)."""
    if not os.path.exists(path):
        return False
    if os.path.isdir(path):
        return any(os.scandir(path))
    return os.path.getsize(path) > 1_000_000


def _node_core(name: str) -> str:
    """Reduce a node/folder name to its distinctive core token.

    ``comfyui-reactor-node`` and ``ComfyUI-ReActor`` both reduce to ``reactor``,
    so a differently-named fork of the same node is recognised as already
    installed (avoids cloning a conflicting duplicate).
    """
    s = name.lower().replace("comfyui", "").replace("node", "")
    return "".join(ch for ch in s if ch.isalnum())


def find_installed_node(nodes_dir: str, node_name: str) -> str:
    """Return the on-disk folder name if this node (or a fork) is present, else ''."""
    exact = os.path.join(nodes_dir, node_name)
    if os.path.isdir(exact):
        return node_name
    if not os.path.isdir(nodes_dir):
        return ""
    core = _node_core(node_name)
    for d in os.scandir(nodes_dir):
        if not d.is_dir():
            continue
        fcore = _node_core(d.name)
        if fcore == core or (len(core) >= 4 and (core in fcore or fcore in core)):
            return d.name
    return ""


# --------------------------------------------------------------------------- #
# Install-location choice (fresh machine, nothing detected)
# --------------------------------------------------------------------------- #
def choose_install_root() -> str:
    """Pick a drive for a fresh ComfyUI install: most free space, prefer non-C."""
    drives = _available_drives()
    best, best_free = None, -1
    for d in drives:
        try:
            free = shutil.disk_usage(d).free
        except OSError:
            continue
        # Prefer a non-system drive with lots of room (matches "keep C: clean").
        weight = free + (50 * 1024**3 if not d.upper().startswith("C") else 0)
        if weight > best_free:
            best, best_free = d, weight
    return best or "C:\\"


# --------------------------------------------------------------------------- #
# STEP 1 - ComfyUI + venv
# --------------------------------------------------------------------------- #
def step_comfyui(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                 args: argparse.Namespace) -> None:
    banner("STEP 1/6  ComfyUI + virtual environment")
    spec = manifest.get("comfyui", {})

    comfy_dir = state.get("comfy_dir") or cfg.comfy_dir
    if not comfy_dir:
        root = args.comfy_dir or os.path.join(choose_install_root(), "comfyui", "ComfyUI")
        comfy_dir = _norm(root)
    state["comfy_dir"] = comfy_dir

    # 1a. clone ComfyUI if missing
    if os.path.exists(os.path.join(comfy_dir, "main.py")):
        skip(f"ComfyUI already present: {comfy_dir}")
    else:
        if not shutil.which("git"):
            fail("git not found on PATH -- install Git for Windows first.")
            return
        parent = os.path.dirname(comfy_dir)
        if not args.readonly:
            os.makedirs(parent, exist_ok=True)
        run(["git", "clone", spec.get("repo", "https://github.com/comfyanonymous/ComfyUI.git"),
             comfy_dir], dry=args.readonly)

    # 1b. create venv next to ComfyUI (parent/venv) if missing
    venv_dir = os.path.join(os.path.dirname(comfy_dir), "venv")
    venv_py = os.path.join(venv_dir, "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        venv_py_posix = os.path.join(venv_dir, "bin", "python")
        if os.path.exists(venv_py_posix):
            venv_py = venv_py_posix
    if os.path.exists(venv_py):
        skip(f"venv already present: {venv_dir}")
    else:
        base_py = cfg.system_python or sys.executable
        info(f"creating venv with {base_py}")
        run([base_py, "-m", "venv", venv_dir], dry=args.readonly)
        if os.name != "nt":
            venv_py = os.path.join(venv_dir, "bin", "python")
    state["comfy_python"] = _norm(venv_py)

    if args.readonly:
        info("(read-only) would install torch + ComfyUI requirements")
        state.setdefault("output_dir", _norm(os.path.join(os.path.dirname(comfy_dir), "output")))
        return

    # 1c. torch (cu121) then ComfyUI requirements -- pip skips already-satisfied.
    run([venv_py, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    torch_pkgs = spec.get("torch_packages", [])
    index = spec.get("torch_index_url")
    if torch_pkgs:
        cmd = [venv_py, "-m", "pip", "install", *torch_pkgs]
        if index:
            cmd += ["--index-url", index]
        run(cmd, check=False)
    req = os.path.join(comfy_dir, spec.get("requirements", "requirements.txt"))
    if os.path.exists(req):
        run([venv_py, "-m", "pip", "install", "-r", req], check=False)

    out_dir = os.path.join(os.path.dirname(comfy_dir), "output")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(comfy_dir, "input"), exist_ok=True)
    state.setdefault("output_dir", _norm(out_dir))
    ok(f"ComfyUI ready at {comfy_dir}")


# --------------------------------------------------------------------------- #
# STEP 2 - custom nodes + numpy pin
# --------------------------------------------------------------------------- #
def step_nodes(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
               args: argparse.Namespace) -> None:
    banner("STEP 2/6  ComfyUI custom nodes")
    comfy_dir = state.get("comfy_dir") or cfg.comfy_dir
    venv_py = state.get("comfy_python") or cfg.comfy_python
    if not comfy_dir:
        fail("no ComfyUI dir known -- run the comfyui step first.")
        return
    nodes_dir = os.path.join(comfy_dir, "custom_nodes")
    os.makedirs(nodes_dir, exist_ok=True)

    if not shutil.which("git"):
        fail("git not found on PATH -- cannot clone nodes.")
        return

    nodes = manifest.get("custom_nodes", [])
    installed_any = False
    for node in nodes:
        if not node.get("required", False) and not args.include_optional:
            skip(f"{node['name']} (optional)")
            continue
        dest = os.path.join(nodes_dir, node["name"])
        found = find_installed_node(nodes_dir, node["name"])
        if found:
            skip(f"{node['name']} already present"
                 + (f" (as '{found}')" if found != node["name"] else ""))
            # keep the existing (possibly fork) folder's requirements path
            dest = os.path.join(nodes_dir, found)
        else:
            cmd = ["git", "clone"]
            if node.get("recurse_submodules"):
                cmd.append("--recurse-submodules")
            cmd += [node["repo"], dest]
            run(cmd, dry=args.readonly)
            installed_any = True
        # per-node pip requirements
        req = os.path.join(dest, "requirements.txt")
        if os.path.exists(req) and not args.readonly:
            run([venv_py, "-m", "pip", "install", "-r", req], check=False)
            installed_any = True

    # Re-force critical pins AFTER node installs (order matters!).
    if installed_any and not args.readonly:
        for pin in manifest.get("pip_pins", []):
            info(f"pinning {pin['spec']} ({pin.get('reason','')})")
            run([venv_py, "-m", "pip", "install", pin["spec"]], check=False)
    elif args.readonly:
        for pin in manifest.get("pip_pins", []):
            info(f"(read-only) would pin {pin['spec']}")
    ok("custom nodes done")
    warn("ReActor needs InsightFace: if its pip build failed, install the prebuilt "
         "cp311 wheel from github.com/Gourieff/Assets, then re-run.")


# --------------------------------------------------------------------------- #
# STEP 3 - model files (HuggingFace / URL)
# --------------------------------------------------------------------------- #
def _download_hf_file(repo: str, filename: str, dest_dir: str, rename_to: Optional[str],
                      hf_cache: Optional[str]) -> str:
    from huggingface_hub import hf_hub_download
    os.makedirs(dest_dir, exist_ok=True)
    kwargs = dict(repo_id=repo, filename=filename, local_dir=dest_dir)
    if hf_cache:
        kwargs["cache_dir"] = hf_cache
    got = hf_hub_download(**kwargs)
    final = os.path.join(dest_dir, os.path.basename(rename_to or filename))
    got_abs = os.path.abspath(got)
    if os.path.abspath(final) != got_abs:
        os.makedirs(os.path.dirname(final), exist_ok=True)
        shutil.copyfile(got_abs, final)
    return final


def _download_hf_snapshot(repo: str, dest_dir: str, hf_cache: Optional[str]) -> str:
    from huggingface_hub import snapshot_download
    os.makedirs(dest_dir, exist_ok=True)
    kwargs = dict(repo_id=repo, local_dir=dest_dir)
    if hf_cache:
        kwargs["cache_dir"] = hf_cache
    snapshot_download(**kwargs)
    return dest_dir


def _download_url(url: str, dest: str, expected_mb: Optional[float]) -> str:
    """Streaming download with HTTP-range resume and a tqdm progress bar."""
    import requests
    from tqdm import tqdm
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    pos = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    headers = {"Range": f"bytes={pos}-"} if pos else {}
    with requests.get(url, headers=headers, stream=True, timeout=60,
                      allow_redirects=True) as r:
        if r.status_code == 416:  # already fully downloaded
            os.replace(tmp, dest)
            return dest
        r.raise_for_status()
        total = int(r.headers.get("Content-Length", 0)) + pos
        mode = "ab" if pos else "wb"
        with open(tmp, mode) as fh, tqdm(
            total=total or None, initial=pos, unit="B", unit_scale=True,
            desc=os.path.basename(dest)[:28], leave=False,
        ) as bar:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    fh.write(chunk)
                    bar.update(len(chunk))
    os.replace(tmp, dest)
    return dest


def _extract_zip(zip_path: str, dest_dir: str) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def step_models(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                args: argparse.Namespace) -> Dict[str, int]:
    banner("STEP 3/6  model files")
    # Rebuild a config view that knows the freshly-installed comfy dir.
    live = _live_config(cfg, state)
    hf_cache = live.hf_cache_dir or None
    if hf_cache:
        os.environ.setdefault("HF_HOME", hf_cache)

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    file_models = [m for m in manifest.get("models", [])
                   if m.get("source", {}).get("type") != "ollama"]
    if not args.dry_run and not args.list_only:
        if not _ensure_pip_deps():
            fail("downloader deps unavailable -- skipping model downloads.")
            return stats

    for m in file_models:
        required = m.get("required", False)
        if not required and not args.include_optional:
            skip(f"{m['name']} (optional, {human_mb(m.get('approx_size_mb'))})")
            continue
        dest = model_target_path(live, m)
        src = m["source"]
        if is_present(m, dest) and not args.force:
            skip(f"{m['name']} -- present ({human_mb(m.get('approx_size_mb'))})")
            stats["skipped"] += 1
            continue
        if args.list_only or args.dry_run:
            info(f"WOULD GET {m['name']} ({human_mb(m.get('approx_size_mb'))}) -> {dest}")
            continue

        info(f"downloading {m['name']} ({human_mb(m.get('approx_size_mb'))})")
        info(f"    -> {dest}")
        try:
            stype = src["type"]
            if stype == "hf_file":
                _download_hf_file(src["repo"], src["file"], os.path.dirname(dest),
                                  src.get("rename_to"), hf_cache)
            elif stype == "hf_snapshot":
                _download_hf_snapshot(src["repo"], dest, hf_cache)
            elif stype == "url":
                if src.get("extract") == "zip":
                    tmp_zip = dest.rstrip("\\/") + ".zip"
                    _download_url(src["url"], tmp_zip, m.get("approx_size_mb"))
                    os.makedirs(dest, exist_ok=True)
                    _extract_zip(tmp_zip, dest)
                    try:
                        os.remove(tmp_zip)
                    except OSError:
                        pass
                else:
                    _download_url(src["url"], dest, m.get("approx_size_mb"))
            else:
                warn(f"unknown source type '{stype}' for {m['name']}")
                stats["failed"] += 1
                continue
            ok(f"{m['name']}")
            stats["downloaded"] += 1
        except Exception as exc:  # keep going; report at the end
            fail(f"{m['name']}: {exc}")
            if m.get("license_note", "").lower().find("login") >= 0:
                warn("this repo may be gated -- run 'huggingface-cli login' and retry.")
            stats["failed"] += 1
    return stats


# --------------------------------------------------------------------------- #
# STEP 4 - Ollama models
# --------------------------------------------------------------------------- #
def step_ollama(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                args: argparse.Namespace) -> Dict[str, int]:
    banner("STEP 4/6  Ollama models")
    live = _live_config(cfg, state)
    stats = {"pulled": 0, "skipped": 0, "failed": 0}

    ollama = live.ollama_exe or shutil.which("ollama") or "ollama"
    env_overlay = live.ollama_env()
    if not (shutil.which("ollama") or (live.ollama_exe and os.path.exists(live.ollama_exe))):
        warn("ollama executable not found -- install the Ollama app first "
             "(https://ollama.com). Skipping LLM pulls.")
        return stats

    # Which tags already exist?
    present: set = set()
    if not args.dry_run:
        try:
            out = subprocess.run([ollama, "list"], capture_output=True, text=True,
                                 env={**os.environ, **env_overlay}, timeout=30).stdout
            for line in out.splitlines()[1:]:
                if line.strip():
                    present.add(line.split()[0])
        except Exception as exc:
            warn(f"could not run 'ollama list': {exc}")

    tags = [m for m in manifest.get("models", [])
            if m.get("source", {}).get("type") == "ollama"]
    for m in tags:
        tag = m["target_relative_path"]
        required = m.get("required", False)
        if not required and not args.include_optional:
            skip(f"{tag} (optional, {human_mb(m.get('approx_size_mb'))})")
            continue
        if tag in present and not args.force:
            skip(f"{tag} -- present")
            stats["skipped"] += 1
            continue
        if args.list_only or args.dry_run:
            info(f"WOULD PULL {tag} ({human_mb(m.get('approx_size_mb'))})")
            continue
        rc = run([ollama, "pull", tag], env_overlay=env_overlay, check=False)
        if rc == 0:
            ok(tag)
            stats["pulled"] += 1
        else:
            fail(f"{tag} (pull exit {rc}; tag may not exist in the Ollama library yet)")
            stats["failed"] += 1
    return stats


# --------------------------------------------------------------------------- #
# STEP 5 - local code-RAG (Qdrant + fastembed)
# --------------------------------------------------------------------------- #
def step_rag(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
             args: argparse.Namespace) -> None:
    banner("STEP 5/6  local code-RAG (Qdrant + embeddings)")
    live = _live_config(cfg, state)
    req = REPO_ROOT / "rag" / "requirements.txt"
    if not req.exists():
        warn(f"rag/requirements.txt not found ({req}) -- skipping RAG setup.")
        return

    # A dedicated venv keeps the RAG's fastapi/qdrant/fastembed deps isolated
    # from ComfyUI's. Location is drive-agnostic (under %LOCALAPPDATA%).
    base = _rag_base_dir()
    venv_dir = os.path.join(base, "venv")
    venv_py = os.path.join(venv_dir, "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        posix_py = os.path.join(venv_dir, "bin", "python")
        if os.path.exists(posix_py):
            venv_py = posix_py
    base_py = live.system_python or sys.executable

    if args.readonly:
        info(f"(read-only) would create RAG venv at {venv_dir}")
        info(f"(read-only) would install: {os.path.basename(str(req))} (fastapi, uvicorn, qdrant-client, fastembed)")
        info(f"(read-only) RAG data would live under {base}")
        return

    if os.path.exists(venv_py):
        skip(f"RAG venv present: {venv_dir}")
    else:
        os.makedirs(base, exist_ok=True)
        info(f"creating RAG venv with {base_py}")
        run([base_py, "-m", "venv", venv_dir], check=False)
        if os.name != "nt":
            venv_py = os.path.join(venv_dir, "bin", "python")
    if not os.path.exists(venv_py):
        warn("RAG venv python not found -- installing deps into the base Python instead.")
        venv_py = base_py

    run([venv_py, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    run([venv_py, "-m", "pip", "install", "-r", str(req)], check=False)

    # Pre-create the local data folders so the first server start is clean.
    for d in (live.qdrant_path, live.rag_data_dir, live.rag_cache_dir):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
    ok(f"code-RAG ready. Start it with  rag\\start-rag.cmd  (port {live.rag_port}).")


# --------------------------------------------------------------------------- #
# STEP 6 - write config.json
# --------------------------------------------------------------------------- #
def step_config(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                args: argparse.Namespace) -> None:
    banner("STEP 6/6  write config.json")
    live = _live_config(cfg, state)
    out_path = REPO_ROOT / "config.json"

    resolved_paths = {
        "comfy_dir": live.comfy_dir,
        "comfy_python": live.comfy_python,
        "output_dir": live.output_dir,
        "ollama_exe": live.ollama_exe,
        "ollama_models_dir": live.ollama_models_dir,
        "system_python": live.system_python,
    }
    # Keep only non-empty resolved values.
    resolved_paths = {k: v for k, v in resolved_paths.items() if v}
    new_block = {"paths": resolved_paths}

    existing: Dict[str, Any] = {}
    if out_path.exists() and not args.force:
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
        info(f"merging into existing {out_path.name} (user values kept)")

    # existing user values win; we only fill gaps.
    merged = dict(existing)
    ep = dict(existing.get("paths", {}))
    for k, v in resolved_paths.items():
        ep.setdefault(k, v)
    merged["paths"] = ep

    if args.readonly:
        info("(read-only) would write:")
        print(json.dumps(new_block, indent=2))
        return

    out_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    ok(f"wrote {out_path}")


# --------------------------------------------------------------------------- #
# Helper: a Config that reflects freshly-installed paths in `state`
# --------------------------------------------------------------------------- #
def _live_config(cfg: Config, state: Dict[str, str]) -> Config:
    """Return a Config with `state` overrides layered on top of `cfg`."""
    if not state:
        return cfg
    data = cfg.raw()
    data.setdefault("paths", {})
    for k, v in state.items():
        if v:
            data["paths"][k] = v
    return Config(data, source=cfg.source)


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Vulture AI bootstrap installer (idempotent).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--steps", default="all",
                    help="comma list of steps to run: " + ",".join(STEP_ORDER) + " (default: all)")
    ap.add_argument("--all", action="store_true",
                    help="include optional models AND optional custom nodes")
    ap.add_argument("--optional", dest="include_optional", action="store_true",
                    help="include items marked optional in the manifest")
    ap.add_argument("--list", dest="list_only", action="store_true",
                    help="show present/missing items, download nothing")
    ap.add_argument("--dry-run", action="store_true", help="print planned actions only")
    ap.add_argument("--force", action="store_true",
                    help="re-download / overwrite even if present")
    ap.add_argument("--comfy-dir", default="",
                    help="where to install ComfyUI on a fresh machine")
    ap.add_argument("--config", default=None, help="path to an existing config.json to read")
    args = ap.parse_args(argv)

    if args.all:
        args.include_optional = True
    # --list and --dry-run are both read-only: never clone/pip/write in those modes.
    args.readonly = bool(args.dry_run or args.list_only)

    cfg = load_config(args.config)
    manifest = load_manifest()

    banner("Vulture AI  --  bootstrap installer")
    info(f"repo root      : {REPO_ROOT}")
    info(f"config source  : {cfg.source}")
    info(f"ComfyUI (found): {cfg.comfy_dir or '(none -- will install)'}")
    info(f"Ollama (found) : {cfg.ollama_exe or '(none -- install the Ollama app)'}")
    info(f"optional items : {'YES' if args.include_optional else 'no (use --all)'}")
    if args.dry_run:
        info("MODE: dry-run (no changes)")
    if args.list_only:
        info("MODE: list only")

    steps = STEP_ORDER if args.steps == "all" else [s.strip() for s in args.steps.split(",")]
    state: Dict[str, str] = {}
    summary: Dict[str, Any] = {}

    for step in steps:
        if step == "comfyui":
            step_comfyui(cfg, state, manifest, args)
        elif step == "nodes":
            step_nodes(cfg, state, manifest, args)
        elif step == "models":
            summary["models"] = step_models(cfg, state, manifest, args)
        elif step == "ollama":
            summary["ollama"] = step_ollama(cfg, state, manifest, args)
        elif step == "rag":
            step_rag(cfg, state, manifest, args)
        elif step == "config":
            step_config(cfg, state, manifest, args)
        else:
            warn(f"unknown step '{step}' -- valid: {', '.join(STEP_ORDER)}")

    banner("SUMMARY")
    if "models" in summary:
        s = summary["models"]
        info(f"model files : {s['downloaded']} downloaded, {s['skipped']} present, {s['failed']} failed")
    if "ollama" in summary:
        s = summary["ollama"]
        info(f"ollama      : {s['pulled']} pulled, {s['skipped']} present, {s['failed']} failed")
    failed = sum(summary.get(k, {}).get("failed", 0) for k in ("models", "ollama"))
    if failed:
        warn(f"{failed} item(s) failed -- see messages above. Re-running is safe (resumes).")
    print("\n  Next: python setup/verify.py   (checks the whole install)\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
