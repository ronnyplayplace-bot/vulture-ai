"""
title: Chat Memory (local RAG long-term memory)
author: Overlkd Studio
version: 1.0
description: Pulls relevant project context from the LOCAL Code/Chat-RAG (Qdrant)
             and injects it before the model, and stores user + assistant messages
             back as chat memory. 100% local — points at http://127.0.0.1:8001 by
             default, no server, nothing leaves your machine.
required_open_webui_version: 0.5.0
"""
# How to install in Open WebUI:
#   Admin Panel -> Functions -> "+"  -> paste this whole file -> Save.
#   Open the function's settings (gear) if you want to change the Valves; the
#   defaults are fine (they point at the local RAG on 127.0.0.1:8001).
#   Enable the filter per model/chat with the toggle.
# This turns the same local RAG that powers "Code search" into chat memory too:
# code is stored as type="code", chat as type="chat" — one local store, two uses.

from typing import Optional
from pydantic import BaseModel, Field
import re
import requests

# Strip reasoning blocks so only real content goes into memory.
_REASONING = re.compile(r"<details[^>]*type=\"reasoning\".*?</details>", re.DOTALL | re.IGNORECASE)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _clean(text: str) -> str:
    text = _REASONING.sub("", text)
    text = _THINK.sub("", text)
    return text.strip()


def _is_internal_task(body: dict) -> bool:
    """True for Open WebUI internal calls (title/tags/follow-ups/autocomplete)."""
    md = body.get("metadata") or {}
    return bool(md.get("task"))


class Filter:
    class Valves(BaseModel):
        memory_api_url: str = Field(
            default="http://127.0.0.1:8001",
            description="URL of the LOCAL RAG server (the same one 'Code search' uses).",
        )
        api_key: str = Field(default="", description="Optional bearer token; empty = no auth (local default).")
        project: str = Field(default="default", description="Current project namespace.")
        top_k: int = Field(default=12, description="Number of context chunks to retrieve (5-20).")
        max_chars: int = Field(default=12000, description="Max characters of context injected.")
        enabled: bool = Field(default=True, description="Memory on/off.")
        store_chat: bool = Field(default=True, description="Automatically store chats into memory.")
        timeout: int = Field(default=15, description="HTTP timeout in seconds.")

    def __init__(self):
        self.valves = self.Valves()

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.valves.api_key:
            h["Authorization"] = f"Bearer {self.valves.api_key}"
        return h

    def _resolve_project(self, text: str):
        """Allow a per-message override:  #p:projectname  at the start of a line.
        Returns (project, cleaned_text)."""
        project = self.valves.project
        clean = text
        for line in text.splitlines():
            s = line.strip()
            if s.lower().startswith("#p:"):
                project = s[3:].strip() or project
                clean = text.replace(line, "", 1).strip()
                break
        return project, clean

    def _post(self, path, payload):
        return requests.post(
            f"{self.valves.memory_api_url}{path}",
            headers=self._headers(), json=payload, timeout=self.valves.timeout,
        )

    # ---- inlet: before the model ----------------------------------------
    def inlet(self, body: dict, __user__: Optional[dict] = None, **kwargs) -> dict:
        if not self.valves.enabled or _is_internal_task(body):
            return body
        messages = body.get("messages", [])
        idx = next((i for i in range(len(messages) - 1, -1, -1)
                    if messages[i].get("role") == "user"), None)
        if idx is None:
            return body

        raw = messages[idx].get("content", "")
        if not isinstance(raw, str) or not raw.strip():
            return body
        project, clean = self._resolve_project(raw)
        if clean != raw:
            messages[idx]["content"] = clean  # remove the #p: tag from the model input

        # 1) retrieve context
        try:
            ctx = self._post("/context", {
                "project": project, "query": clean,
                "top_k": self.valves.top_k, "max_chars": self.valves.max_chars,
            }).json().get("context", "")
        except Exception as e:
            ctx = ""
            print(f"[chat_memory] context error: {e}")

        if ctx:
            sys_block = {
                "role": "system",
                "content": (
                    "You have access to this project's long-term memory. Use the "
                    "retrieved context below when relevant, and do not contradict it "
                    "without reason:\n\n" + ctx
                ),
            }
            insert_at = 1 if messages and messages[0].get("role") == "system" else 0
            messages.insert(insert_at, sys_block)
            body["messages"] = messages

        # 2) store the user message as chat memory
        if self.valves.store_chat:
            try:
                self._post("/memory", {
                    "project": project, "type": "chat",
                    "text": clean, "source": "openwebui:user",
                })
            except Exception as e:
                print(f"[chat_memory] store user error: {e}")

        body.setdefault("_chat_memory", {})["project"] = project
        return body

    # ---- outlet: after the model ----------------------------------------
    def outlet(self, body: dict, __user__: Optional[dict] = None, **kwargs) -> dict:
        if not self.valves.enabled or not self.valves.store_chat or _is_internal_task(body):
            return body
        project = (body.get("_chat_memory") or {}).get("project", self.valves.project)
        messages = body.get("messages", [])
        raw_reply = next((m.get("content") for m in reversed(messages)
                          if m.get("role") == "assistant"), None)
        reply = _clean(raw_reply) if isinstance(raw_reply, str) else None
        if reply and reply.strip():
            try:
                self._post("/memory", {
                    "project": project, "type": "chat",
                    "text": reply, "source": "openwebui:assistant",
                })
            except Exception as e:
                print(f"[chat_memory] store assistant error: {e}")
        return body
