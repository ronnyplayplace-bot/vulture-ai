# -*- coding: utf-8 -*-
"""Vulture AI (Overlkd Studio) -- post-install self-test.

Prints a clear OK / FAIL checklist for the whole environment so you know a
fresh clone + ``python setup/install.py`` actually produced a *working* setup:

    * config resolves and points at real folders
    * ComfyUI is installed and its venv Python works
    * numpy is pinned to 1.26.4 (ReActor / LivePortrait requirement)
    * the required custom nodes are on disk
    * the core model files exist (FLUX, upscaler, checkpoint, face-swap, ...)
    * Ollama answers and has the required model
    * (optional, --start-comfy) ComfyUI actually boots, the port opens, and the
      key custom-node class types are registered via /object_info

Usage::

    python setup/verify.py                # static + live probes of what's running
    python setup/verify.py --start-comfy  # also boot ComfyUI and check nodes load
    python setup/verify.py --all          # also check optional items

Exit code is non-zero if any REQUIRED check fails (handy for CI / scripts).
Only the standard library is used.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vulture.config import load_config, Config  # noqa: E402

MANIFEST_PATH = Path(__file__).resolve().parent / "models.manifest.json"

# Representative class_type each required node registers (checked via /object_info).
NODE_CLASS_PROBES = {
    "ComfyUI-GGUF": "UnetLoaderGGUF",
    "ComfyUI_UltimateSDUpscale": "UltimateSDUpscale",
    "comfyui-reactor-node": "ReActorFaceSwap",
    "ComfyUI-LivePortraitKJ": "LivePortraitProcess",
    "ComfyUI-VideoHelperSuite": "VHS_LoadVideo",
}


class Checklist:
    """Collects pass/fail results and prints them with a final tally."""

    def __init__(self) -> None:
        self.rows: List[Tuple[str, bool, bool, str]] = []  # label, passed, required, detail

    def add(self, label: str, passed: bool, required: bool = True, detail: str = "") -> bool:
        self.rows.append((label, passed, required, detail))
        mark = "OK  " if passed else ("FAIL" if required else "warn")
        tail = f"  ({detail})" if detail else ""
        print(f"  [{mark}] {label}{tail}")
        return passed

    def section(self, title: str) -> None:
        print(f"\n--- {title} ---")

    def failed_required(self) -> int:
        return sum(1 for _, p, req, _ in self.rows if req and not p)

    def failed_optional(self) -> int:
        return sum(1 for _, p, req, _ in self.rows if not req and not p)


# --------------------------------------------------------------------------- #
# Small probes
# --------------------------------------------------------------------------- #
def port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def http_json(url: str, timeout: float = 8.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def file_ok(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 1_000_000


def dir_nonempty(path: str) -> bool:
    return bool(path) and os.path.isdir(path) and any(os.scandir(path))


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def check_config(cfg: Config, cl: Checklist) -> None:
    cl.section("Configuration")
    cl.add(f"config source: {cfg.source}", True, detail="")
    cl.add("comfy_dir set", bool(cfg.comfy_dir), detail=cfg.comfy_dir)
    cl.add("output_dir set", bool(cfg.output_dir), detail=cfg.output_dir)
    cl.add("comfy_api", True, detail=cfg.comfy_api)
    cl.add("ollama_api", True, detail=cfg.ollama_api)


def check_comfy_install(cfg: Config, cl: Checklist) -> None:
    cl.section("ComfyUI install")
    main_py = os.path.join(cfg.comfy_dir, "main.py") if cfg.comfy_dir else ""
    cl.add("ComfyUI main.py", os.path.isfile(main_py), detail=main_py)
    cl.add("venv python", os.path.isfile(cfg.comfy_python), detail=cfg.comfy_python)

    # numpy pin (critical for ReActor + LivePortrait)
    ver = ""
    passed = False
    if os.path.isfile(cfg.comfy_python):
        try:
            ver = subprocess.run(
                [cfg.comfy_python, "-c", "import numpy;print(numpy.__version__)"],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip()
            passed = ver == "1.26.4"
        except Exception as exc:
            ver = f"error: {exc}"
    cl.add("numpy == 1.26.4 in ComfyUI venv", passed, detail=ver or "not checked")


def _node_core(name: str) -> str:
    """Normalise a node/folder name to its distinctive core token.

    ``comfyui-reactor-node`` and ``ComfyUI-ReActor`` both reduce to ``reactor``,
    so verification tolerates the many alternate fork folder names.
    """
    s = name.lower().replace("comfyui", "").replace("node", "")
    return "".join(ch for ch in s if ch.isalnum())


def check_nodes(cfg: Config, manifest: dict, cl: Checklist, include_optional: bool) -> None:
    cl.section("Custom nodes (on disk)")
    nodes_dir = cfg.comfy_custom_nodes_dir
    existing = []
    if os.path.isdir(nodes_dir):
        existing = [(d.name, _node_core(d.name)) for d in os.scandir(nodes_dir) if d.is_dir()]

    def present(node_name: str) -> Tuple[bool, str]:
        exact = os.path.join(nodes_dir, node_name)
        if os.path.isdir(exact):
            return True, ""
        core = _node_core(node_name)
        for folder, fcore in existing:
            if fcore == core or (len(core) >= 4 and (core in fcore or fcore in core)):
                return True, f"found as '{folder}'"
        return False, ""

    for node in manifest.get("custom_nodes", []):
        req = node.get("required", False)
        if not req and not include_optional:
            continue
        found, detail = present(node["name"])
        cl.add(f"node {node['name']}", found, required=req, detail=detail)


def check_models(cfg: Config, manifest: dict, cl: Checklist, include_optional: bool) -> None:
    from install import model_target_path, is_present  # reuse resolver
    cl.section("Model files")
    for m in manifest.get("models", []):
        if m.get("source", {}).get("type") == "ollama":
            continue
        req = m.get("required", False)
        if not req and not include_optional:
            continue
        path = model_target_path(cfg, m)
        cl.add(m["name"], is_present(m, path), required=req, detail="")


def check_ollama(cfg: Config, manifest: dict, cl: Checklist, include_optional: bool) -> None:
    cl.section("Ollama")
    up = port_open(cfg.host, cfg.ollama_port)
    cl.add(f"Ollama API reachable ({cfg.ollama_api})", up, required=True,
           detail="start the Ollama app if this fails")
    tags = set()
    if up:
        try:
            data = http_json(f"{cfg.ollama_api}/api/tags")
            tags = {mm.get("name", "") for mm in data.get("models", [])}
            tags |= {t.split(":")[0] for t in list(tags)}  # allow bare-name match
        except Exception as exc:
            cl.add("Ollama /api/tags", False, detail=str(exc))
    for m in manifest.get("models", []):
        if m.get("source", {}).get("type") != "ollama":
            continue
        req = m.get("required", False)
        if not req and not include_optional:
            continue
        tag = m["target_relative_path"]
        present = tag in tags or tag.split(":")[0] in tags
        cl.add(f"ollama model {tag}", present if up else False, required=req)


def check_comfy_live(cfg: Config, cl: Checklist, start: bool) -> None:
    cl.section("ComfyUI runtime")
    running = port_open(cfg.host, cfg.comfy_port)
    started_proc: Optional[subprocess.Popen] = None

    if not running and start:
        cl.add("ComfyUI not running -> starting it for the test", True, detail="")
        try:
            started_proc = subprocess.Popen(
                cfg.comfy_start_command(), shell=True,
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
            )
        except Exception as exc:
            cl.add("launch ComfyUI", False, detail=str(exc))
        for _ in range(90):  # wait up to ~180s
            if port_open(cfg.host, cfg.comfy_port):
                running = True
                break
            time.sleep(2)

    if not running:
        cl.add(f"ComfyUI port {cfg.comfy_port} open", False, required=start,
               detail="not running -- pass --start-comfy to boot it, or start the studio")
        return

    cl.add(f"ComfyUI port {cfg.comfy_port} open", True)
    try:
        info = http_json(f"{cfg.comfy_api}/object_info", timeout=30)
        registered = set(info.keys())
        for node_name, class_type in NODE_CLASS_PROBES.items():
            cl.add(f"node loads: {class_type} ({node_name})", class_type in registered,
                   required=True)
    except Exception as exc:
        cl.add("query /object_info", False, detail=str(exc))

    if started_proc is not None:
        # We started it only for the test -> shut our instance down again.
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{cfg.comfy_api}/free",
                                       data=b'{"unload_models":true,"free_memory":true}',
                                       headers={"Content-Type": "application/json"}),
                timeout=5,
            )
        except Exception:
            pass
        try:
            started_proc.terminate()
        except Exception:
            pass
        cl.add("stopped the test ComfyUI instance", True, required=False)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Vulture AI install self-test.")
    ap.add_argument("--all", dest="include_optional", action="store_true",
                    help="also verify optional models / nodes")
    ap.add_argument("--start-comfy", action="store_true",
                    help="boot ComfyUI to confirm it starts and nodes register")
    ap.add_argument("--config", default=None, help="path to a config.json")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    print("=" * 64)
    print("  Vulture AI  --  install verification")
    print("=" * 64)

    cl = Checklist()
    check_config(cfg, cl)
    check_comfy_install(cfg, cl)
    check_nodes(cfg, manifest, cl, args.include_optional)
    check_models(cfg, manifest, cl, args.include_optional)
    check_ollama(cfg, manifest, cl, args.include_optional)
    check_comfy_live(cfg, cl, args.start_comfy)

    print("\n" + "=" * 64)
    req_fail = cl.failed_required()
    opt_fail = cl.failed_optional()
    if req_fail == 0:
        print(f"  RESULT: OK  -- all required checks passed"
              f"{f' ({opt_fail} optional warning(s))' if opt_fail else ''}.")
    else:
        print(f"  RESULT: {req_fail} REQUIRED check(s) failed"
              f"{f', {opt_fail} optional warning(s)' if opt_fail else ''}.")
        print("  Fix: re-run  python setup/install.py  (it resumes / skips what's done).")
    print("=" * 64)
    return 1 if req_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
