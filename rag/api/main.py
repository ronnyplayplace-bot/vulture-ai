# -*- coding: utf-8 -*-
"""Vulture AI -- local, private code-RAG server.

A tiny FastAPI service that lets you index YOUR OWN projects / GitHub repos and
search them semantically.  Everything is local:

  - Qdrant     : vector store, embedded (a local folder -- NOT a server).
  - fastembed  : CPU-friendly ONNX embeddings (bge-small by default, no PyTorch).
  - FastAPI    : a small REST surface the indexer (``ingest.py``) and the UI use.

Nothing is uploaded and nothing is shared.  Bind it to ``127.0.0.1`` only.

Data model:
  One collection (default ``vulture_code``).  Each chunk is a Qdrant point with
  the payload: ``project, type, text, source, ts, chunk_index, doc_id``.
  Search is filtered by ``project`` (and optionally by ``type``).

Chunk ``type`` is free-form but validated against a small vocabulary so the UI
can colour/filter results:
  ``goal | code | decision | error | architecture | chat | note``

Configuration is read from the environment (the ``start-rag.cmd`` launcher fills
these in from ``config.json`` via ``vulture/batenv.py``; sensible local defaults
apply when unset, so ``uvicorn main:app`` also works standalone):

  QDRANT_PATH           local Qdrant folder      (default: <base>/qdrant)
  RAG_DATA_DIR          project registry folder  (default: <base>/data)
  FASTEMBED_CACHE_PATH  embedding model cache    (default: <base>/cache)
  EMBED_MODEL           fastembed model name     (default: BAAI/bge-small-en-v1.5)
  RAG_COLLECTION        Qdrant collection name   (default: vulture_code)
  MEMORY_API_KEY        optional bearer token    (default: "" -> no auth)
  RAG_HOST / RAG_PORT   bind address for __main__ (default: 127.0.0.1 / 8001)

where ``<base>`` is ``%LOCALAPPDATA%/VultureAI/rag`` on Windows and
``~/.local/share/VultureAI/rag`` elsewhere.
"""
import os
import time
import uuid
import json
from typing import List, Optional, Dict, Any
from contextlib import asynccontextmanager


# --- offline fast-path (must run BEFORE the fastembed import reads the env) ---
def _cache_has_model(cache_dir: str) -> bool:
    """True if a completed model snapshot (an .onnx file) is already cached."""
    if not cache_dir or not os.path.isdir(cache_dir):
        return False
    for root, _dirs, files in os.walk(cache_dir):
        if any(f.endswith(".onnx") for f in files):
            return True
    return False


def _early_cache_dir() -> str:
    """CACHE_DIR resolution, duplicated here because it is needed pre-import."""
    base = os.environ.get("LOCALAPPDATA", "") if os.name == "nt" else ""
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.getenv("FASTEMBED_CACHE_PATH") or os.path.join(base, "VultureAI", "rag", "cache")


if _cache_has_model(_early_cache_dir()):
    # The model is fully cached -> never touch the network on boot. Without this
    # a stalled HuggingFace metadata request hangs the server for minutes at
    # "Waiting for application startup" (observed live: CDN socket in CloseWait).
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm
from fastembed import TextEmbedding

from chunking import chunk_text, est_tokens


# --------------------------------------------------------------------------- #
# Configuration (environment-driven, drive-agnostic local defaults)
# --------------------------------------------------------------------------- #
def _rag_base_dir() -> str:
    """Drive-agnostic base folder for the RAG's private data.

    Mirrors ``vulture.config._rag_base_dir`` so the server has the same defaults
    whether it is started by the launcher or directly with uvicorn.
    """
    base = os.environ.get("LOCALAPPDATA", "") if os.name == "nt" else ""
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "VultureAI", "rag")


_BASE = _rag_base_dir()
QDRANT_PATH = os.getenv("QDRANT_PATH") or os.path.join(_BASE, "qdrant")
DATA_DIR    = os.getenv("RAG_DATA_DIR") or os.getenv("DATA_DIR") or os.path.join(_BASE, "data")
CACHE_DIR   = os.getenv("FASTEMBED_CACHE_PATH") or os.path.join(_BASE, "cache")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
COLLECTION  = os.getenv("RAG_COLLECTION") or os.getenv("COLLECTION") or "vulture_code"
API_KEY     = os.getenv("MEMORY_API_KEY", "")  # optional; empty string == no auth
HOST        = os.getenv("RAG_HOST", "127.0.0.1")
PORT        = int(os.getenv("RAG_PORT", "8001"))
# bge models retrieve better when the query carries this instruction prefix:
QUERY_PREFIX = os.getenv(
    "QUERY_PREFIX",
    "Represent this sentence for searching relevant passages: ",
)

VALID_TYPES = {"goal", "code", "decision", "error", "architecture", "chat", "note"}

state: Dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# Project registry (a small JSON file next to the vector store)
# --------------------------------------------------------------------------- #
def _projects_file() -> str:
    return os.path.join(DATA_DIR, "projects.json")


def load_projects() -> Dict[str, Any]:
    try:
        with open(_projects_file(), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_projects(p: Dict[str, Any]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _projects_file() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _projects_file())


# --------------------------------------------------------------------------- #
# Embedding  (chunking lives in chunking.py -- sized for the 512-token model)
# --------------------------------------------------------------------------- #
def embed_docs(texts: List[str]) -> List[List[float]]:
    return [v.tolist() for v in state["emb"].embed(texts)]


def embed_query(text: str) -> List[float]:
    return list(state["emb"].embed([QUERY_PREFIX + text]))[0].tolist()


# --------------------------------------------------------------------------- #
# Lifespan: load the embedding model + open the local vector store
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    offline = bool(os.environ.get("HF_HUB_OFFLINE"))
    print(f"[rag] loading embedding model ({EMBED_MODEL}"
          f"{', offline from cache' if offline else ', may download ~90 MB on first run'}) ...",
          flush=True)
    try:
        emb = TextEmbedding(model_name=EMBED_MODEL, cache_dir=CACHE_DIR)
    except Exception:
        if not offline:
            raise
        # Cache looked complete but wasn't -- flip back online and retry once.
        print("[rag] cached model unusable -- retrying online ...", flush=True)
        os.environ.pop("HF_HUB_OFFLINE", None)
        try:
            from huggingface_hub import constants as _hfc
            _hfc.HF_HUB_OFFLINE = False
        except Exception:
            pass
        emb = TextEmbedding(model_name=EMBED_MODEL, cache_dir=CACHE_DIR)
    state["emb"] = emb
    state["dim"] = len(list(emb.embed(["dimension probe"]))[0])
    # Always embedded/local: a Qdrant *folder*, never a network server.
    print(f"[rag] opening local store ({QDRANT_PATH}) ...", flush=True)
    os.makedirs(QDRANT_PATH, exist_ok=True)
    client = QdrantClient(path=QDRANT_PATH)
    state["client"] = client
    names = [c.name for c in client.get_collections().collections]
    if COLLECTION not in names:
        client.create_collection(
            COLLECTION,
            vectors_config=qm.VectorParams(size=state["dim"], distance=qm.Distance.COSINE),
        )
        client.create_payload_index(COLLECTION, "project", qm.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "type", qm.PayloadSchemaType.KEYWORD)
    yield


app = FastAPI(title="Vulture AI Code-RAG", version="1.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Auth (optional -- only enforced when MEMORY_API_KEY is non-empty)
# --------------------------------------------------------------------------- #
def check_auth(authorization: Optional[str]) -> None:
    if API_KEY and authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid or missing token")


ALL_PROJECTS = {"*", "_all_", "all", "", None}


def _filter(project, types: Optional[List[str]]):
    """``project`` in ALL_PROJECTS => no project restriction (search everything)."""
    must = []
    if project not in ALL_PROJECTS:
        must.append(qm.FieldCondition(key="project", match=qm.MatchValue(value=project)))
    if types:
        must.append(qm.FieldCondition(key="type", match=qm.MatchAny(any=list(types))))
    return qm.Filter(must=must) if must else None


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ProjectIn(BaseModel):
    name: str
    goals: Optional[str] = None
    description: Optional[str] = None


class MemoryIn(BaseModel):
    project: str
    type: str = "note"
    text: str
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SearchIn(BaseModel):
    project: str
    query: str
    top_k: int = 8
    types: Optional[List[str]] = None
    min_score: float = 0.0


class ContextIn(BaseModel):
    project: str
    query: str
    top_k: int = 12
    max_chars: int = 12000
    types: Optional[List[str]] = None
    min_score: float = 0.4  # default relevance floor: inject only matching chunks (no noise)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok", "model": EMBED_MODEL, "dim": state.get("dim"), "collection": COLLECTION}


@app.get("/stats")
def stats(authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    c = state["client"]
    info = c.get_collection(COLLECTION)
    return {"points": info.points_count, "projects": list(load_projects().keys())}


@app.post("/projects")
def create_project(p: ProjectIn, authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    projects = load_projects()
    if p.name not in projects:
        projects[p.name] = {"name": p.name, "description": p.description or "",
                            "created": time.time()}
        save_projects(projects)
    # Store the goals/description straight away as searchable memory.
    added = 0
    if p.goals:
        added += _store(p.name, "goal", p.goals, source="project:goals")
    if p.description:
        added += _store(p.name, "architecture", p.description, source="project:description")
    return {"project": p.name, "chunks_indexed": added}


@app.get("/projects")
def list_projects(authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    return {"projects": list(load_projects().values())}


@app.get("/projects/{name}")
def get_project(name: str, authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    projects = load_projects()
    if name not in projects:
        raise HTTPException(404, "project not found")
    c = state["client"]
    counts = {}
    for t in VALID_TYPES:
        r = c.count(COLLECTION, count_filter=_filter(name, [t]), exact=True)
        counts[t] = r.count
    return {"project": projects[name], "chunk_counts": counts}


@app.delete("/projects/{name}")
def delete_project(name: str, types: Optional[str] = None,
                   authorization: Optional[str] = Header(None)):
    """Delete a project's chunks. ``?types=code`` (comma list) limits deletion to
    those chunk types and keeps the registry entry -- ingest.py uses this to
    clear the old code index before re-indexing (no duplicates), while chat
    memory stored under the same project name survives."""
    check_auth(authorization)
    if name in ALL_PROJECTS:
        raise HTTPException(400, "refusing to delete across all projects")
    tlist = [t.strip() for t in types.split(",") if t.strip()] if types else None
    c = state["client"]
    c.delete(COLLECTION, points_selector=qm.FilterSelector(filter=_filter(name, tlist)))
    if not tlist:
        projects = load_projects()
        projects.pop(name, None)
        save_projects(projects)
    return {"deleted": name, "types": tlist or "all"}


def _store(project: str, mtype: str, text: str, source: Optional[str] = None,
           metadata: Optional[Dict[str, Any]] = None) -> int:
    if mtype not in VALID_TYPES:
        mtype = "note"
    chunks = chunk_text(text)
    if not chunks:
        return 0
    vectors = embed_docs(chunks)
    doc_id = str(uuid.uuid4())
    ts = time.time()
    points = []
    for idx, (ch, vec) in enumerate(zip(chunks, vectors)):
        payload = {"project": project, "type": mtype, "text": ch,
                   "source": source or "", "ts": ts, "chunk_index": idx, "doc_id": doc_id}
        if metadata:
            payload["metadata"] = metadata
        points.append(qm.PointStruct(id=str(uuid.uuid4()), vector=vec, payload=payload))
    state["client"].upsert(COLLECTION, points=points)
    return len(points)


@app.post("/memory")
def add_memory(m: MemoryIn, authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    # Auto-register the project on first write.
    projects = load_projects()
    if m.project not in projects:
        projects[m.project] = {"name": m.project, "description": "", "created": time.time()}
        save_projects(projects)
    n = _store(m.project, m.type, m.text, m.source, m.metadata)
    return {"project": m.project, "type": m.type, "chunks_indexed": n}


@app.post("/search")
def search(s: SearchIn, authorization: Optional[str] = Header(None)):
    check_auth(authorization)
    qv = embed_query(s.query)
    hits = state["client"].query_points(
        COLLECTION, query=qv, query_filter=_filter(s.project, s.types),
        limit=max(1, min(s.top_k, 50)), with_payload=True,
        score_threshold=(s.min_score if s.min_score > 0 else None),
    ).points
    return {"results": [{
        "score": round(h.score, 4),
        "project": h.payload.get("project"),
        "type": h.payload.get("type"),
        "source": h.payload.get("source"),
        "ts": h.payload.get("ts"),
        "text": h.payload.get("text"),
    } for h in hits]}


@app.post("/context")
def build_context(c: ContextIn, authorization: Optional[str] = Header(None)):
    """Retrieval + a ready-to-inject context string (bounded by ``max_chars``)."""
    check_auth(authorization)
    qv = embed_query(c.query)
    hits = state["client"].query_points(
        COLLECTION, query=qv, query_filter=_filter(c.project, c.types),
        limit=max(1, min(c.top_k, 50)), with_payload=True,
        score_threshold=(c.min_score if c.min_score > 0 else None),
    ).points
    blocks, used, total = [], 0, 0
    for h in hits:
        txt = h.payload.get("text", "")
        header = f"[{h.payload.get('type','note')}" + (f" | {h.payload.get('source')}" if h.payload.get("source") else "") + "]"
        block = f"{header}\n{txt}"
        if total + len(block) > c.max_chars:
            break
        blocks.append(block)
        total += len(block)
        used += 1
    context = (
        f"## Relevant project context (project: {c.project})\n\n"
        + "\n\n---\n\n".join(blocks)
    ) if blocks else ""
    return {
        "project": c.project,
        "context": context,
        "chunks_used": used,
        "char_len": total,
        "token_estimate": est_tokens(context),
    }


# --------------------------------------------------------------------------- #
# Standalone entry point:  python main.py  (the launcher uses uvicorn directly)
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
