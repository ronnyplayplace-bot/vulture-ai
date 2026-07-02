# -*- coding: utf-8 -*-
"""Chunking must stay inside the embedding model's 512-token window --
anything past it is silently dropped by fastembed and unfindable in search."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rag", "api"))
from chunking import chunk_text, est_tokens  # noqa: E402


def test_empty_text():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_one_chunk():
    text = "word " * 100
    assert chunk_text(text) == [text.strip()]


def test_chunks_fit_embedding_window():
    text = " ".join(f"w{i}" for i in range(20_000))
    for ch in chunk_text(text):
        assert est_tokens(ch) <= 512, "chunk exceeds bge-small's 512-token window"


def test_no_words_lost():
    words = [f"w{i}" for i in range(5_000)]
    chunks = chunk_text(" ".join(words))
    assert len(chunks) > 1
    seen = set()
    for ch in chunks:
        seen.update(ch.split())
    assert seen == set(words)


def test_consecutive_chunks_overlap():
    chunks = chunk_text(" ".join(f"w{i}" for i in range(2_000)))
    for a, b in zip(chunks, chunks[1:]):
        assert set(a.split()) & set(b.split()), "adjacent chunks share no overlap"
