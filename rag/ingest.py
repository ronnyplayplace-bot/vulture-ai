#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Index a codebase into the local Vulture AI code-RAG (code/text files only).

Walks a folder and sends each source file to the local RAG server's ``/memory``
endpoint.  Nothing leaves your machine -- the server stores everything in a local
embedded Qdrant folder.

Usage::

    python ingest.py <project_name> <path>

    # index this repo under the name "myapp":
    python ingest.py myapp C:\\code\\myapp

    # a GitHub project you cloned locally:
    git clone https://github.com/you/project D:\\code\\project
    python ingest.py project D:\\code\\project

Environment:

    MEMORY_API_URL   base URL of the local RAG server (default http://127.0.0.1:8001)
    MEMORY_API_KEY   optional bearer token; leave empty for the default (no auth)
"""
import os
import sys
import time
import json
import urllib.parse
import urllib.request

API_URL = os.getenv("MEMORY_API_URL", "http://127.0.0.1:8001")
API_KEY = os.getenv("MEMORY_API_KEY", "")  # optional; empty == no auth header

CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
            ".php", ".gd", ".cs", ".java", ".kt", ".swift", ".rb", ".go", ".rs",
            ".c", ".cpp", ".h", ".hpp", ".html", ".htm", ".css", ".scss", ".sass",
            ".less", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
            ".sql", ".sh", ".bash", ".ps1", ".bat", ".md", ".txt", ".gradle",
            ".tscn", ".tres", ".gdshader"}
SKIP_DIRS = {"node_modules", ".git", ".godot", ".import", "vendor", "dist", "build",
             ".next", "__pycache__", "venv", ".venv", "target", "bin", "obj",
             ".idea", ".vscode", "out", "coverage", ".gradle"}
MAX_BYTES = 150_000  # skip larger files (e.g. minified / generated)


def post(path, payload):
    """POST JSON to the local RAG server. Adds a bearer header only if a key is set."""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        API_URL + path, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def clear_code_index(project):
    """Drop the project's previous *code* chunks (chat memory survives).

    Without this every re-index of the same project piles duplicate chunks
    into the store. Best-effort: on any error (first index, server down)
    indexing simply proceeds."""
    headers = {}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    url = f"{API_URL}/projects/{urllib.parse.quote(project, safe='')}?types=code"
    req = urllib.request.Request(url, headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=120):
            print(f"Cleared previous code index of '{project}'.")
    except Exception:
        pass


def main():
    if len(sys.argv) < 3:
        print("Usage: ingest.py <project_name> <path>")
        sys.exit(2)
    project, root = sys.argv[1], sys.argv[2]
    if not os.path.isdir(root):
        print("Path not found:", root)
        sys.exit(1)

    clear_code_index(project)
    files, chunks, skipped, bytes_sent = 0, 0, 0, 0
    t0 = time.time()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in CODE_EXT:
                continue
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(fp) > MAX_BYTES:
                    skipped += 1
                    continue
                with open(fp, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                skipped += 1
                continue
            if not content.strip():
                continue
            rel = os.path.relpath(fp, root).replace("\\", "/")
            text = f"// FILE: {rel}\n\n{content}"
            try:
                res = post("/memory", {"project": project, "type": "code",
                                       "text": text, "source": rel})
                files += 1
                chunks += res.get("chunks_indexed", 0)
                bytes_sent += len(content)
                if files % 10 == 0:
                    print(f"  {files} files | {chunks} chunks | {rel}")
            except Exception as e:
                print("  Error on", rel, "->", e)
                skipped += 1
    dt = time.time() - t0
    print(f"\nDONE '{project}': {files} files, {chunks} chunks, "
          f"{skipped} skipped, {bytes_sent // 1024} KB in {dt:.0f}s")


if __name__ == "__main__":
    main()
