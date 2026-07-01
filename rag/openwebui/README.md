# Chat memory (optional) — local, via Open WebUI

The local RAG that powers **Code search** can also give your **chat** a long-term
memory. Same server, same embedded store — code is saved as `type="code"`, chat as
`type="chat"`. Nothing leaves your machine.

## Install

1. Make sure the local RAG is running (the **Code search** window can start it, or
   run `rag/start-rag.cmd`). It listens on `http://127.0.0.1:8001`.
2. In **Open WebUI**: `Admin Panel → Functions → +`, paste the whole contents of
   [`ai_memory_filter.py`](ai_memory_filter.py), and **Save**.
3. Enable the filter for a model/chat with its toggle. The defaults already point
   at the local RAG — you normally don't need to change any Valve.

## What it does

- **Before** each message it retrieves relevant context from the local RAG and
  injects it, so the model "remembers" earlier conversations.
- **After** each turn it stores your message and the reply back as `type="chat"`.
- Per-message override: start a line with `#p:myproject` to file that message
  under a specific project namespace.

Turn it off any time with the `enabled` / `store_chat` Valves. It's completely
optional — the studio works fine without it.
