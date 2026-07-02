# -*- coding: utf-8 -*-
"""Word-based chunking sized for the embedding model (stdlib only, unit-testable).

bge-small-en-v1.5 truncates every input at 512 tokens -- anything past that in a
chunk is silently NOT embedded and therefore unfindable in search. So chunks
must stay comfortably below that window: ~400 tokens (~300 words) with a
50-token overlap. (The old 1500-token target threw away ~2/3 of every chunk.)
"""
from typing import List


def chunk_text(text: str, target_tokens: int = 400, overlap_tokens: int = 50) -> List[str]:
    """Split ``text`` into word chunks of ~``target_tokens`` (~0.75 words/token)."""
    words = text.split()
    if not words:
        return []
    wpc = max(50, int(target_tokens * 0.75))
    ov = max(0, int(overlap_tokens * 0.75))
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + wpc]))
        if i + wpc >= len(words):
            break
        i += (wpc - ov)
    return out


def est_tokens(text: str) -> int:
    return int(len(text.split()) / 0.75) + 1
