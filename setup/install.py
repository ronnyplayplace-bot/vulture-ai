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
    Config, load_config, _available_drives, _norm, _rag_base_dir, query_gpu,
)

MANIFEST_PATH = Path(__file__).resolve().parent / "models.manifest.json"
STEP_ORDER = ["comfyui", "nodes", "models", "ollama", "aider", "webui", "rag", "studio", "config"]

#: Every fail() lands here so the SUMMARY + exit code reflect step errors too
#: (a failed ComfyUI clone must not end in "Setup complete").
FAILURES: List[str] = []


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
    FAILURES.append(msg)
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


def source_page(src: Dict[str, Any]) -> str:
    """Human-facing page where a model can be downloaded by hand.

    hf_file / hf_snapshot -> the HuggingFace repo page; url -> the file URL.
    Used for the "get it yourself" manual instructions of non-commercial models.
    """
    stype = src.get("type")
    if stype in ("hf_file", "hf_snapshot"):
        return "https://huggingface.co/" + src.get("repo", "")
    if stype == "url":
        return src.get("url", "")
    return src.get("url") or src.get("repo", "")


def _dir_has_payload(path: str, min_bytes: int = 1_000_000) -> bool:
    """True if the directory holds at least one real file >= ``min_bytes``.

    Dot-dirs (e.g. huggingface_hub's ``.cache``) are ignored: an interrupted
    snapshot download leaves only ``.cache`` behind and must NOT count as
    installed, or the model is skipped forever on re-runs."""
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in files:
            try:
                if os.path.getsize(os.path.join(root, fn)) >= min_bytes:
                    return True
            except OSError:
                pass
    return False


def is_present(entry: Dict[str, Any], path: str) -> bool:
    """Existence check: file >1MB, or a directory with real payload files."""
    if not os.path.exists(path):
        return False
    if os.path.isdir(path):
        return _dir_has_payload(path)
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
    repo = spec.get("repo", "https://github.com/comfyanonymous/ComfyUI.git")
    if os.path.exists(os.path.join(comfy_dir, "main.py")):
        skip(f"ComfyUI already present: {comfy_dir}")
    elif args.readonly:
        info(f"(read-only) would clone ComfyUI into {comfy_dir}")
    else:
        if not shutil.which("git"):
            fail("git not found on PATH -- install Git for Windows first.")
            return
        parent = os.path.dirname(comfy_dir)
        os.makedirs(parent, exist_ok=True)
        if os.path.isdir(comfy_dir) and os.listdir(comfy_dir):
            # Dir exists but has no main.py (an interrupted/re-run install left just
            # custom_nodes etc.). A plain `git clone` into a non-empty dir fails hard
            # (exit 128) and we must NOT proceed with a broken ComfyUI. Clone to a temp
            # dir and merge the core in, preserving any already-installed custom_nodes.
            info(f"ComfyUI dir exists but is incomplete -- fetching ComfyUI core into {comfy_dir}")
            tmp = comfy_dir + ".tmp_clone"
            shutil.rmtree(tmp, ignore_errors=True)
            run(["git", "clone", repo, tmp])
            for name in os.listdir(tmp):
                src = os.path.join(tmp, name)
                dst = os.path.join(comfy_dir, name)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
                elif name == "custom_nodes" and os.path.isdir(src):
                    for sub in os.listdir(src):  # add ComfyUI's default nodes, keep ours
                        d2 = os.path.join(dst, sub)
                        if not os.path.exists(d2):
                            shutil.move(os.path.join(src, sub), d2)
            shutil.rmtree(tmp, ignore_errors=True)
        else:
            run(["git", "clone", repo, comfy_dir])
        if not os.path.exists(os.path.join(comfy_dir, "main.py")):
            fail(f"ComfyUI clone did not produce main.py in {comfy_dir} -- cannot continue.")
            return

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
    # Blackwell (RTX 50xx, compute capability >= 10): the cu121 wheels have no
    # sm_120 kernels -- torch would import but refuse to run on the GPU.
    gpu = query_gpu()
    if gpu and gpu.get("compute_cap", 0) >= 10.0 and spec.get("torch_packages_blackwell"):
        info(f"Blackwell GPU detected (compute {gpu['compute_cap']}) -> using cu128 torch")
        torch_pkgs = spec["torch_packages_blackwell"]
        index = spec.get("torch_index_url_blackwell", index)
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
    if not args.readonly:  # --list/--dry-run must not create stray folders
        os.makedirs(nodes_dir, exist_ok=True)

    if not shutil.which("git"):
        fail("git not found on PATH -- cannot clone nodes.")
        return

    nodes = manifest.get("custom_nodes", [])
    installed_any = False
    missing_required = []
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
            rc = run(cmd, dry=args.readonly)
            # A failed clone must NOT pass silently (that is how the disabled
            # ReActor repo left face-swap broken). Surface it, name the node.
            if not args.readonly and (rc != 0 or not os.path.isdir(dest)):
                fail(f"{node['name']}: clone FAILED from {node['repo']}")
                if node.get("required"):
                    missing_required.append(node["name"])
                continue
            installed_any = True
        # per-node pip requirements
        req = os.path.join(dest, "requirements.txt")
        if os.path.exists(req) and not args.readonly:
            run([venv_py, "-m", "pip", "install", "-r", req], check=False)
            installed_any = True
        # Nodes needing a prebuilt wheel on Windows (ReActor -> InsightFace):
        # source builds need MSVC, so use Gourieff's cp311 wheel + onnxruntime-gpu.
        wheel = node.get("insightface_wheel")
        if wheel and not args.readonly:
            info(f"installing prebuilt InsightFace wheel for {node['name']}")
            run([venv_py, "-m", "pip", "install", wheel], check=False)
            run([venv_py, "-m", "pip", "uninstall", "-y", "onnxruntime"], check=False)
            run([venv_py, "-m", "pip", "install", "onnxruntime-gpu"], check=False)
            installed_any = True

    # Re-force critical pins AFTER node installs (order matters!).
    if installed_any and not args.readonly:
        for pin in manifest.get("pip_pins", []):
            info(f"pinning {pin['spec']} ({pin.get('reason','')})")
            run([venv_py, "-m", "pip", "install", pin["spec"]], check=False)
    elif args.readonly:
        for pin in manifest.get("pip_pins", []):
            info(f"(read-only) would pin {pin['spec']}")

    # Verify InsightFace actually imports (ReActor's hard requirement).
    if not args.readonly and os.path.exists(venv_py):
        rc = run([venv_py, "-c", "import insightface"], check=False)
        if rc != 0:
            warn("InsightFace is NOT importable -- face-swap (ReActor) will not work.")
            warn('Fix: "' + venv_py + '" -m pip install '
                 "https://github.com/Gourieff/Assets/raw/main/Insightface/"
                 "insightface-0.7.3-cp311-cp311-win_amd64.whl")
            warn('then re-pin: "' + venv_py + '" -m pip install numpy==1.26.4')

    if missing_required:
        fail("required custom node(s) failed to install: " + ", ".join(missing_required))
    ok("custom nodes done")


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
        # rename, don't copy -- copyfile left a multi-GB duplicate behind
        os.replace(got_abs, final)
    return final


def _download_hf_snapshot(repo: str, dest_dir: str, hf_cache: Optional[str],
                          allow_patterns: Optional[List[str]] = None) -> str:
    from huggingface_hub import snapshot_download
    os.makedirs(dest_dir, exist_ok=True)
    kwargs = dict(repo_id=repo, local_dir=dest_dir)
    if hf_cache:
        kwargs["cache_dir"] = hf_cache
    if allow_patterns:  # e.g. ["*.safetensors"] -> skip an unsafe/optional pickle in the repo
        kwargs["allow_patterns"] = allow_patterns
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
        if pos and r.status_code != 206:
            pos = 0  # server ignored the Range header -> appending would corrupt; restart
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


def _fetch_model(live: Config, m: Dict[str, Any], hf_cache: Optional[str]) -> str:
    """Download ONE model to its manifest target. Raises on error / unknown type.

    Used both by the bulk 'models' step and by the studio's per-model
    "Get it" button (--get), so the file always lands at the exact path and
    name Vulture expects -- the user never has to rename anything by hand.
    """
    dest = model_target_path(live, m)
    src = m["source"]
    stype = src["type"]
    if stype == "hf_file":
        _download_hf_file(src["repo"], src["file"], os.path.dirname(dest),
                          src.get("rename_to"), hf_cache)
    elif stype == "hf_snapshot":
        _download_hf_snapshot(src["repo"], dest, hf_cache, src.get("allow_patterns"))
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
        raise ValueError(f"unknown source type '{stype}'")
    return dest


def step_get(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
             args: argparse.Namespace) -> int:
    """Explicit, user-initiated download of specific models by name (--get NAME).

    This is the ONLY path that will fetch a non-commercial model, and only
    because the user clicked its "Get it (I accept the license)" button in the
    studio. Nothing here runs during a normal 'Install everything'.
    """
    banner("Get model(s) -- explicit, user-requested download")
    if not _ensure_pip_deps():
        fail("downloader deps unavailable.")
        return 1
    live = _live_config(cfg, state)
    hf_cache = live.hf_cache_dir or None
    if hf_cache:
        os.environ.setdefault("HF_HOME", hf_cache)
    by_name = {m["name"]: m for m in manifest.get("models", [])}
    failed = 0
    for name in args.get:
        m = by_name.get(name)
        if not m:
            fail(f"no model named '{name}' in the manifest.")
            failed += 1
            continue
        if m.get("license"):
            info(f"license: {m['name']} -- {m['license']} "
                 "(non-commercial: governs how you may USE it, not the download itself)")
        info(f"downloading {m['name']} ({human_mb(m.get('approx_size_mb'))})")
        try:
            dest = _fetch_model(live, m, hf_cache)
            ok(f"{m['name']} -> {dest}")
        except Exception as exc:
            fail(f"{m['name']}: {exc}")
            failed += 1
    return 1 if failed else 0


def step_models(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                args: argparse.Namespace) -> Dict[str, int]:
    banner("STEP 3/6  model files")
    # Rebuild a config view that knows the freshly-installed comfy dir.
    live = _live_config(cfg, state)
    hf_cache = live.hf_cache_dir or None
    if hf_cache:
        os.environ.setdefault("HF_HOME", hf_cache)

    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "failed_names": []}
    nc_skipped = 0  # non-commercial models Vulture NEVER downloads (user gets them manually)
    file_models = [m for m in manifest.get("models", [])
                   if m.get("source", {}).get("type") != "ollama"]
    if not args.dry_run and not args.list_only:
        if not _ensure_pip_deps():
            fail("downloader deps unavailable -- skipping model downloads.")
            return stats

    for m in file_models:
        # Non-commercial models are NEVER downloaded by Vulture. Regardless of any
        # flag we always skip here -- BEFORE reaching any _download_* call -- and
        # instead print manual "get it yourself" instructions. (personal/research
        # licenses; the user fetches them and drops them in the folder themselves.)
        if m.get("noncommercial"):
            lic = m.get("license") or m.get("license_note") or "non-commercial"
            page = m.get("page_url") or source_page(m.get("source", {}))
            target = model_target_path(live, m)
            note = m.get("manual_note", "")
            info(f"MANUAL (non-commercial, get it yourself): {m['name']} [{lic}] "
                 f"-> open {page} and place at {target}" + (f"  ({note})" if note else ""))
            nc_skipped += 1
            continue
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
            _fetch_model(live, m, hf_cache)
            ok(f"{m['name']}")
            stats["downloaded"] += 1
        except Exception as exc:  # keep going; report at the end
            fail(f"{m['name']}: {exc}")
            if m.get("license_note", "").lower().find("login") >= 0:
                warn("this repo may be gated -- run 'huggingface-cli login' and retry.")
            stats["failed"] += 1
            stats["failed_names"].append(m["name"])
    if nc_skipped:
        info(f"[note] {nc_skipped} non-commercial model(s) are NOT downloaded by Vulture. "
             "Open the studio's \"Setup\" -> Manual models section for links + folders.")
    return stats


# --------------------------------------------------------------------------- #
# STEP 4 - Ollama models
# --------------------------------------------------------------------------- #
def step_ollama(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                args: argparse.Namespace) -> Dict[str, int]:
    banner("STEP 4/6  Ollama models")
    live = _live_config(cfg, state)
    stats = {"pulled": 0, "skipped": 0, "failed": 0, "failed_names": []}

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
            stats["failed_names"].append(tag)
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
    # from ComfyUI's. Use rag_base so the venv lands exactly where rag_python
    # looks for it -- honouring install_base (e.g. D:), not a hardcoded C: path.
    base = live.rag_base
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
# STEP 5a - Aider coding agent (local-model pair programmer)
# --------------------------------------------------------------------------- #
def _tool_base_dir(name: str, install_base: str = "") -> str:
    """Private base for a tool's venv. Honours install_base (e.g. D:) so big
    venvs (Open WebUI ~7 GB) don't fill C:; falls back to %LOCALAPPDATA%."""
    if install_base:
        return os.path.join(install_base, "VultureAI", name)
    base = os.environ.get("LOCALAPPDATA", "") if os.name == "nt" else ""
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "VultureAI", name)


def step_aider(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
               args: argparse.Namespace) -> None:
    banner("STEP 5a  Aider coding agent (uses your local Ollama models)")
    live = _live_config(cfg, state)
    base = _tool_base_dir("aider", live.install_base)
    venv_dir = os.path.join(base, "venv")
    venv_py = os.path.join(venv_dir, "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        posix_py = os.path.join(venv_dir, "bin", "python")
        if os.path.exists(posix_py):
            venv_py = posix_py
    base_py = live.system_python or sys.executable

    if args.readonly:
        info(f"(read-only) would create Aider venv at {venv_dir}")
        info("(read-only) would pip install aider-chat")
        return

    if os.path.exists(venv_py):
        skip(f"Aider venv present: {venv_dir}")
    else:
        os.makedirs(base, exist_ok=True)
        info(f"creating Aider venv with {base_py}")
        run([base_py, "-m", "venv", venv_dir], check=False)
        if os.name != "nt":
            venv_py = os.path.join(venv_dir, "bin", "python")
    if not os.path.exists(venv_py):
        warn("Aider venv python not found -- cannot install aider.")
        return

    run([venv_py, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    run([venv_py, "-m", "pip", "install",
         "--upgrade-strategy", "only-if-needed", "aider-chat"], check=False)
    # Record the resolved python so step_config writes aider_python -> config.json
    # (batenv.py then exports %AIDER_PY% for Overlkd-Coder.cmd).
    state["aider_python"] = _norm(venv_py)
    rc = run([venv_py, "-m", "aider", "--version"], check=False)
    if rc == 0:
        ok("Aider ready. Launch via Overlkd-Coder.cmd (uses your local Ollama models).")
    else:
        warn("aider --version failed; check the pip output above.")


# --------------------------------------------------------------------------- #
# STEP 5b - Open WebUI (local chat frontend for Ollama, ~7 GB, Python 3.11)
# --------------------------------------------------------------------------- #
def _default_chat_model(manifest: Dict[str, Any], live: Config) -> str:
    """The manifest's default chat tier (the one flagged ``default``), so the
    launcher env and the seeded DB config agree on the same starting model."""
    for m in manifest.get("models", []):
        cp = m.get("chat_profile") or {}
        if cp.get("default") and m.get("source", {}).get("type") == "ollama":
            return m["target_relative_path"]
    return live.coder_model or "qwen2.5-coder:7b"


def _write_start_webui_cmd(live: Config, venv_dir: str, webui_data: str,
                           default_model: str) -> None:
    """(Re)write rag/start-webui.cmd + start-webui.vbs from resolved config.

    SECURITY: `open-webui serve` defaults to binding 0.0.0.0 -- with
    WEBUI_AUTH=False that would expose an admin chat (incl. code-executing
    Functions) to the whole LAN. Always pass --host 127.0.0.1 here.
    pythonw + a VBS shim = no console window at all. Single local user (no login)."""
    port = live.webui_port
    host = live.host or "127.0.0.1"
    ollama = live.ollama_api or "http://127.0.0.1:11434"
    exe = os.path.join(venv_dir, "Scripts", "open-webui.exe")
    out = REPO_ROOT / "rag" / "start-webui.cmd"
    lines = [
        "@echo off",
        "REM Vulture AI -- Open WebUI (local chat). Written by setup/install.py.",
        "title Vulture AI - Chat (Open WebUI)",
        f'set "DATA_DIR={webui_data}"',
        f'set "OLLAMA_BASE_URL={ollama}"',
        'set "WEBUI_AUTH=False"',
        'set "ENABLE_SIGNUP=False"',
        'set "DEFAULT_USER_ROLE=admin"',
        f'set "DEFAULT_MODELS={default_model}"',
        'set "GLOBAL_LOG_LEVEL=WARNING"',
        'set "DO_NOT_TRACK=true"',
        'set "SCARF_NO_ANALYTICS=true"',
        # open-webui serve sets its own secret keys + runs migrations. The studio
        # launches this via start-webui.vbs (window style 0 -> no visible console,
        # so the request-log chatter is never seen). Run the .cmd directly to debug.
        # --host 127.0.0.1 is mandatory (see the docstring): no-auth admin chat
        # must never listen on the network.
        f'"{exe}" serve --host {host} --port {port}',
    ]
    out.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", errors="replace")
    ok(f"wrote {out}")
    # Hidden launcher: runs the .cmd with window style 0 (nothing visible at all).
    vbs = REPO_ROOT / "rag" / "start-webui.vbs"
    vbs_body = ('Set sh = CreateObject("WScript.Shell")\r\n'
                f'sh.Run "cmd /c ""{out}""", 0, False\r\n')
    vbs.write_text(vbs_body, encoding="ascii", errors="replace")


def _seed_webui_function(live: Config, venv_py: str, webui_data: str,
                         manifest: Dict[str, Any]) -> None:
    """Warm-boot Open WebUI once to make it turnkey: persist the Ollama connection,
    import + globally enable the Chat-RAG memory filter, and build the curated chat
    model profiles (friendly English tiers, raw models hidden, default = fastest).
    All best-effort -- on any failure the UI still works, just not pre-seeded."""
    import json as _json, time as _time
    import urllib.request as _u, urllib.error as _ue
    filt = REPO_ROOT / "rag" / "openwebui" / "ai_memory_filter.py"
    if not filt.exists():
        return
    base = f"http://127.0.0.1:{live.webui_port}"

    def _api(method, path, token=None, body=None):
        data = _json.dumps(body).encode() if body is not None else None
        req = _u.Request(base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", "Bearer " + token)
        with _u.urlopen(req, timeout=30) as r:
            return _json.loads(r.read().decode() or "{}")

    env = os.environ.copy()
    env.update({
        "DATA_DIR": webui_data,
        "OLLAMA_BASE_URL": live.ollama_api or "http://127.0.0.1:11434",
        # WEBUI_ADMIN_EMAIL/PASSWORD => the server bootstraps this admin at startup
        # on a fresh DB (deterministic, independent of WEBUI_AUTH). ENABLE_SIGNUP=True
        # only for this transient warm-boot so the signup fallback can create the
        # first admin if needed (the runtime launcher keeps signup off).
        "WEBUI_AUTH": "False", "ENABLE_SIGNUP": "True", "DEFAULT_USER_ROLE": "admin",
        "WEBUI_ADMIN_EMAIL": "admin@localhost", "WEBUI_ADMIN_PASSWORD": "admin",
        "DEFAULT_MODELS": _default_chat_model(manifest, live),
        "GLOBAL_LOG_LEVEL": "WARNING", "DO_NOT_TRACK": "true", "SCARF_NO_ANALYTICS": "true",
    })
    info("pre-configuring Open WebUI (default model + chat-memory filter)...")
    webui_exe = os.path.join(os.path.dirname(venv_py), "open-webui.exe")
    # Loopback-only, even for this transient warm-boot (signup is enabled here).
    serve_args = ["serve", "--host", "127.0.0.1", "--port", str(live.webui_port)]
    boot_cmd = ([webui_exe, *serve_args]
                if os.path.exists(webui_exe)
                else [venv_py, "-m", "open_webui", *serve_args])
    proc = subprocess.Popen(
        boot_cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        end = _time.time() + 300
        up = False
        while _time.time() < end:
            try:
                _u.urlopen(base + "/health", timeout=5)
                up = True
                break
            except Exception:
                _time.sleep(3)
        if not up:
            warn("Open WebUI did not come up in time -- skipped pre-config (UI still works).")
            return
        # Get an admin token, robust to a fresh vs seeded DB: try signin (works when
        # admin@localhost already exists / WEBUI_AUTH=False auto-creates), else fall
        # back to signup (first user on a fresh DB is force-promoted to admin). Both
        # may 400/403; tolerate that instead of raising.
        def _try(path, body):
            try:
                return _api("POST", path, body=body).get("token")
            except Exception:
                return None
        creds = {"email": "admin@localhost", "password": "admin"}
        token = _try("/api/v1/auths/signin", creds)
        if not token:
            token = _try("/api/v1/auths/signup", {"name": "Admin", **creds})
        if not token:
            token = _try("/api/v1/auths/signin", creds)  # signup may have created it
        if not token:
            warn("could not obtain an Open WebUI admin token -- skipped filter import.")
            return
        # --- 1) Chat-memory filter: import + enable globally. create is the
        # idempotency signal (a by-id GET returns 401 not 404). Re-run: 401 taken.
        content = filt.read_text(encoding="utf-8")
        try:
            _api("POST", "/api/v1/functions/create", token=token, body={
                "id": "ai_memory", "name": "Chat Memory (local RAG)", "content": content,
                "meta": {"description": "Local RAG long-term chat memory", "manifest": {}}})
            _api("POST", "/api/v1/functions/id/ai_memory/toggle", token=token)
            _api("POST", "/api/v1/functions/id/ai_memory/toggle/global", token=token)
            ok("chat-memory filter imported + enabled")
        except _ue.HTTPError:
            ok("chat-memory filter already present")

        # --- 2) Curated chat model profiles: friendly English tiers, raw base models
        # hidden, default = the tier flagged 'default'. Data-driven from the manifest's
        # chat_profile entries. All idempotent (create -> 401 taken -> update).
        EMO = {"Super Fast": "⚡", "Fast": "\U0001f680", "Better": "⚖️",
               "Best": "\U0001f9e0", "Coding": "\U0001f4bb", "Reasoning": "\U0001f52c"}
        PUBLIC = [{"principal_type": "user", "principal_id": "*", "permission": "read"}]

        def _upsert(body):
            try:
                _api("POST", "/api/v1/models/create", token=token, body=body)
            except _ue.HTTPError:
                try:
                    _api("POST", "/api/v1/models/model/update", token=token, body=body)
                except Exception:
                    pass

        profs = sorted(
            [m for m in manifest.get("models", [])
             if m.get("chat_profile") and m.get("source", {}).get("type") == "ollama"],
            key=lambda m: m["chat_profile"].get("order", 99))
        order_ids, default_id = [], None
        for m in profs:
            cp = m["chat_profile"]
            tag = m["target_relative_path"]
            order_ids.append(tag)
            if cp.get("default"):
                default_id = tag
            label = (EMO.get(cp["name"], "") + " " + cp["name"]).strip()
            # IN-PLACE rename of the real base model (base_model_id=None + is_active=True
            # => overrides its display name/meta while keeping it usable). A separate
            # preset pointing at a hidden base 404s with "Model not found" -- do NOT do
            # that. This shows exactly the friendly tier names, and chat works.
            _upsert({"id": tag, "base_model_id": None, "name": label,
                     "meta": {"description": cp.get("hint", ""),
                              "profile_image_url": None, "capabilities": None},
                     "params": {}, "access_grants": PUBLIC, "is_active": True})
        # drop the built-in arena entry so only our tiers show
        try:
            _api("POST", "/api/v1/evaluations/config", token=token,
                 body={"ENABLE_EVALUATION_ARENA_MODELS": False})
        except Exception:
            pass
        # default model + display order
        if default_id:
            try:
                _api("POST", "/api/v1/configs/models", token=token,
                     body={"DEFAULT_MODELS": default_id, "DEFAULT_PINNED_MODELS": None,
                           "MODEL_ORDER_LIST": order_ids})
            except Exception:
                pass
        ok(f"Open WebUI turnkey: {len(profs)} chat models renamed to friendly tiers, "
           f"default = {default_id or 'n/a'}.")
    except Exception as exc:
        warn(f"Open WebUI pre-config skipped ({exc}); the UI still works.")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=15)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def step_webui(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
               args: argparse.Namespace) -> None:
    banner("STEP 5b  Open WebUI (local chat / Ollama frontend)")
    live = _live_config(cfg, state)
    base = _tool_base_dir("webui", live.install_base)
    venv_dir = os.path.join(base, "venv")
    venv_py = os.path.join(venv_dir, "Scripts", "python.exe")
    if not os.path.exists(venv_py):
        posix_py = os.path.join(venv_dir, "bin", "python")
        if os.path.exists(posix_py):
            venv_py = posix_py
    base_py = live.system_python or sys.executable
    webui_data = os.path.join(base, "data")

    if args.readonly:
        info(f"(read-only) would create Open WebUI venv at {venv_dir}")
        info("(read-only) would pip install open-webui  (~7 GB, Python 3.11 only)")
        return

    if os.path.exists(venv_py):
        skip(f"Open WebUI venv present: {venv_dir}")
    else:
        os.makedirs(base, exist_ok=True)
        info(f"creating Open WebUI venv with {base_py}")
        info("NOTE: Open WebUI needs Python 3.11 (not 3.13).")
        run([base_py, "-m", "venv", venv_dir], check=False)
        if os.name != "nt":
            venv_py = os.path.join(venv_dir, "bin", "python")
    if not os.path.exists(venv_py):
        warn("Open WebUI venv python not found -- cannot install open-webui.")
        return

    run([venv_py, "-m", "pip", "install", "--upgrade", "pip"], check=False)
    info("installing open-webui (this pulls ~7 GB -- can take several minutes)...")
    run([venv_py, "-m", "pip", "install", "--upgrade", "open-webui"], check=False)
    try:
        os.makedirs(webui_data, exist_ok=True)
    except OSError:
        pass
    _write_start_webui_cmd(live, venv_dir, webui_data, _default_chat_model(manifest, live))
    _seed_webui_function(live, venv_py, webui_data, manifest)
    ok(f"Open WebUI ready (turnkey: no login, Ollama connected, memory filter on). "
       f"Chat card / rag\\start-webui.vbs (port {live.webui_port}).")


# --------------------------------------------------------------------------- #
# STEP 5c - Studio GUI runtime deps (into the SYSTEM Python that runs studio.py)
# --------------------------------------------------------------------------- #
STUDIO_DEPS = ["pillow", "websocket-client"]


def step_studio(cfg: Config, state: Dict[str, str], manifest: Dict[str, Any],
                args: argparse.Namespace) -> None:
    banner("STEP 5c  Studio GUI dependencies (Pillow + websocket-client)")
    live = _live_config(cfg, state)
    # studio.py runs on the system Python (the .lnk / Overlkd-Studio.cmd use it),
    # NOT in any venv: Pillow renders the image previews, websocket-client streams
    # the live render progress. Without this step a fresh machine gets a studio
    # whose image windows silently fail to open.
    base_py = live.system_python or sys.executable
    if args.readonly:
        info(f"(read-only) would pip install {' '.join(STUDIO_DEPS)} into {base_py}")
        return
    run([base_py, "-m", "pip", "install",
         "--upgrade-strategy", "only-if-needed", *STUDIO_DEPS], check=False)
    rc = run([base_py, "-c", "import PIL, websocket"], check=False)
    if rc == 0:
        ok("studio deps ready (Pillow + websocket-client)")
    else:
        warn("Pillow/websocket-client still not importable -- the studio will "
             "show a fix hint when an image window is opened.")


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
        "aider_python": live.aider_python,   # Coder (%AIDER_PY%) -- see step_aider
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
# Desktop / folder launcher (a real "Vulture AI" app icon, with the logo)
# --------------------------------------------------------------------------- #
def _find_pythonw(cfg: Config) -> str:
    """Best windowless python (pythonw.exe) so the launcher shows no console."""
    sp = cfg.system_python or ""
    cands = []
    if sp:
        cands.append(os.path.join(os.path.dirname(sp), "pythonw.exe"))
    cands.append(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                              "Programs", "Python", "Python311", "pythonw.exe"))
    cands.append(shutil.which("pythonw") or "")
    for c in cands:
        if c and os.path.exists(c):
            return c
    return "pythonw"  # last resort: rely on PATH


def _write_lnk(lnk: str, target: str, arguments: str, workdir: str,
               icon: str, desc: str) -> bool:
    """Create a Windows .lnk via PowerShell's WScript.Shell (no extra deps)."""
    ps = (
        "$W=New-Object -ComObject WScript.Shell;"
        "$s=$W.CreateShortcut('%s');"
        "$s.TargetPath='%s';"
        "$s.Arguments='%s';"
        "$s.WorkingDirectory='%s';"
        "$s.IconLocation='%s';"
        "$s.Description='%s';"
        "$s.Save()"
    ) % (lnk, target, arguments.replace("'", "''"), workdir, icon, desc)
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       check=False, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        warn(f"shortcut command failed: {exc}")
        return False
    return os.path.exists(lnk)


def make_shortcuts(cfg: Config) -> int:
    """Create a 'Vulture AI' launcher (with the vulture.ico logo) in the install
    folder AND on the Desktop -- so users double-click a real app icon, not a .cmd."""
    if os.name != "nt":
        warn("shortcuts are Windows-only -- skipped.")
        return 0
    app_dir = str(REPO_ROOT)
    studio = os.path.join(app_dir, "studio.py")
    icon = os.path.join(app_dir, "vulture.ico")
    if not os.path.exists(studio):
        fail(f"studio.py not found in {app_dir} -- cannot create a launcher.")
        return 1
    pyw = _find_pythonw(cfg)
    icon_loc = icon if os.path.exists(icon) else pyw
    dests = [os.path.join(app_dir, "Vulture AI.lnk")]
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(desktop):
        dests.append(os.path.join(desktop, "Vulture AI.lnk"))
    made = 0
    for lnk in dests:
        if _write_lnk(lnk, pyw, f'"{studio}"', app_dir, icon_loc,
                      "Vulture AI -- your local, offline AI studio"):
            ok(f"launcher: {lnk}")
            made += 1
        else:
            warn(f"could not create {lnk}")
    if made:
        info("Double-click 'Vulture AI' (with the logo) to start -- Desktop or install folder.")
    return 0 if made else 1


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _python_version(py: str) -> Optional[Tuple[int, int]]:
    """(major, minor) of the interpreter at ``py``, or None if undeterminable."""
    try:
        if os.path.abspath(py) == os.path.abspath(sys.executable):
            return sys.version_info[:2]
        out = subprocess.run(
            [py, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        major, minor = out.split(".")
        return int(major), int(minor)
    except Exception:
        return None


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
    ap.add_argument("--manual-list", action="store_true",
                    help="print one tab-separated line per non-commercial (manual) model and exit; "
                         "used by the studio's Setup window to render the Manual models section")
    ap.add_argument("--get", action="append", default=[], metavar="NAME",
                    help="download ONE model by its manifest name and exit (repeatable). This is the "
                         "only path that fetches a non-commercial model, and only when the user asks "
                         "for it explicitly from the studio's Manual models section.")
    ap.add_argument("--shortcut", action="store_true",
                    help="create a 'Vulture AI' launcher (with the logo) on the Desktop and in the "
                         "install folder, then exit")
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

    # Machine-readable list of the models Vulture never downloads (the GUI parses this).
    # One line per non-commercial model, nothing else -> keep this branch quiet.
    if args.manual_list:
        for m in manifest.get("models", []):
            if not m.get("noncommercial"):
                continue
            lic = m.get("license") or m.get("license_note") or "non-commercial"
            page = m.get("page_url") or source_page(m.get("source", {}))
            target = model_target_path(cfg, m)
            present = 1 if os.path.exists(target) else 0
            note = (m.get("manual_note", "") or "").replace("\t", " ").replace("\n", " ")
            print(f"MANUAL\t{m['name']}\t{lic}\t{page}\t{target}\t{present}\t{note}")
        return 0

    # Explicit per-model download (studio "Get it" button). Handled before the
    # normal step loop so it never touches ComfyUI/venv/config -- just the file.
    if args.get:
        return step_get(cfg, {}, manifest, args)

    # Just (re)create the app launcher and exit (studio button / Create-Icon.cmd).
    if args.shortcut:
        return make_shortcuts(cfg)

    # Hard version gate for real installs: every venv (Open WebUI is 3.11-only)
    # is created from this base Python, and a 3.13 base produces installs that
    # "finish" but don't work. --list / --dry-run stay usable on any version.
    if not args.readonly:
        base_py = cfg.system_python or sys.executable
        vi = _python_version(base_py)
        if vi and not ((3, 11) <= vi <= (3, 12)):
            fail(f"Python {vi[0]}.{vi[1]} at {base_py} -- Vulture needs Python 3.11 (3.12 also works).")
            info("Install Python 3.11 64-bit from https://www.python.org/downloads/")
            info("(tick 'Add python.exe to PATH'), then re-run the installer.")
            return 1

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
        elif step == "aider":
            step_aider(cfg, state, manifest, args)
        elif step == "webui":
            step_webui(cfg, state, manifest, args)
        elif step == "rag":
            step_rag(cfg, state, manifest, args)
        elif step == "studio":
            step_studio(cfg, state, manifest, args)
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
        names = []
        for k in ("models", "ollama"):
            names += summary.get(k, {}).get("failed_names", [])
        warn(f"{failed} item(s) FAILED to download:")
        for n in names:
            warn(f"    - {n}")
        warn("Re-run 'Install everything' to retry -- it resumes and re-tries only "
             "what's still missing (nothing already downloaded is re-fetched).")
    # Step-level errors (failed clones, missing git, ...) must fail the run too --
    # otherwise INSTALL.cmd reports "Setup complete" over a broken install.
    if FAILURES and not args.readonly:
        warn(f"{len(FAILURES)} step error(s):")
        for f in FAILURES:
            warn(f"    - {f}")

    # After a real install, drop a 'Vulture AI' launcher (with the logo) so the
    # user starts from a proper app icon, not a .cmd. Best-effort; never fails the run.
    if not args.readonly and "config" in steps:
        try:
            make_shortcuts(cfg)
        except Exception as exc:
            warn(f"could not create the app launcher: {exc}")

    print("\n  Next: python setup/verify.py   (checks the whole install)\n")
    return 1 if (failed or (FAILURES and not args.readonly)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
