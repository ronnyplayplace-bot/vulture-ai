# Vulture AI — Code-RAG (local, private code search)

Index **your own** projects and cloned GitHub repos, then search them
**semantically** (by meaning, not just keywords). Everything runs locally:

- **Qdrant** (embedded, a local folder — not a server) stores the vectors
- **fastembed** (`bge-small`, CPU/ONNX — no PyTorch) makes the embeddings
- a small **FastAPI** server exposes the endpoints the indexer and the UI use

Nothing is uploaded, nothing is shared. The server binds to `127.0.0.1` only and
needs no API key.

## Setup

The main installer sets this up for you (creates a small dedicated venv and
installs the deps):

```bat
python setup/install.py --steps rag
```

Or install the deps into any Python 3.11 yourself:

```bat
pip install -r rag/requirements.txt
```

Where the data lives (drive-agnostic, off the repo): `%LOCALAPPDATA%\VultureAI\rag`
(Qdrant store, project registry, embedding-model cache). Override the folders
with `qdrant_path` / `rag_data_dir` in `config.json`.

## Start the server

```bat
rag\start-rag.cmd
```

It reads the port / paths / embedding model from `config.json` (via
`vulture\batenv.py`) and starts on `http://127.0.0.1:8001` by default. First run
downloads the small embedding model once into the local cache.

## Index your own projects

```bat
:: python rag\ingest.py <project_name> <path>
python rag\ingest.py myapp C:\code\myapp
```

A GitHub repo — clone it first, then index the local folder:

```bat
git clone https://github.com/you/project D:\code\project
python rag\ingest.py project D:\code\project
```

The indexer walks the folder, skips junk (`node_modules`, `.git`, build output,
big/minified files) and sends each source file to the server. Re-run it any time
to add more; use different `<project_name>` values to keep projects separate.

## Search from the command line

```bat
curl -X POST http://127.0.0.1:8001/search ^
  -H "Content-Type: application/json" ^
  -d "{\"project\":\"myapp\",\"query\":\"where is the login handled\",\"top_k\":5}"
```

Pass `"project": "*"` to search across every indexed project at once.

## Endpoints

| Method | Path               | Purpose                                             |
|--------|--------------------|-----------------------------------------------------|
| GET    | `/health`          | liveness + model/collection info                    |
| GET    | `/stats`           | point count + known projects                        |
| POST   | `/memory`          | index one document (used by `ingest.py`)            |
| POST   | `/search`          | top-K semantic hits as JSON                          |
| POST   | `/context`         | retrieval + a ready-to-inject context string        |
| GET/POST/DELETE | `/projects[/{name}]` | list / register / inspect / delete a project |

**POST `/memory`** — `{ "project": str, "type": "code", "text": str, "source": str? }`
→ `{ "project": str, "type": str, "chunks_indexed": int }`

**POST `/search`** — `{ "project": str, "query": str, "top_k": int?, "types": [str]?, "min_score": float? }`
→ `{ "results": [ { "score": float, "type": str, "source": str, "ts": float, "text": str } ] }`

## Configuration

Set in `config.json` (falls back to sensible local defaults):

| Key | Meaning | Default |
|-----|---------|---------|
| `network.rag_port` | server port | `8001` |
| `paths.qdrant_path` | embedded-Qdrant folder | `%LOCALAPPDATA%\VultureAI\rag\qdrant` |
| `paths.rag_data_dir` | project registry + cache | `%LOCALAPPDATA%\VultureAI\rag\data` |
| `runtime.embed_model` | fastembed model | `BAAI/bge-small-en-v1.5` |
| `runtime.rag_collection` | Qdrant collection | `vulture_code` |
