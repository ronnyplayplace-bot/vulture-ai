# -*- coding: utf-8 -*-
"""The config merge rules are what makes a fresh clone portable -- pin them."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from vulture.config import (  # noqa: E402
    _deep_merge, _strip_comments, _tier_from_vram, load_config,
)


def test_deep_merge_empty_string_keeps_lower_layer():
    # "" in config.json means "unset -> keep auto-detect", never "blank it".
    assert _deep_merge({"a": {"x": 1}}, {"a": {"x": ""}}) == {"a": {"x": 1}}
    assert _deep_merge({"a": {"x": 1}}, {"a": {"x": None}}) == {"a": {"x": 1}}


def test_deep_merge_overrides_and_adds():
    assert _deep_merge({"a": {"x": 1}}, {"a": {"x": 2, "y": 3}}) == {"a": {"x": 2, "y": 3}}


def test_strip_comment_keys():
    assert _strip_comments({"_c": 1, "a": {"//note": 2, "b": 3}}) == {"a": {"b": 3}}


def test_vram_tiers():
    assert _tier_from_vram(6) == "s"
    assert _tier_from_vram(12) == "m"
    assert _tier_from_vram(16) == "l"
    assert _tier_from_vram(24) == "xl"


def test_defaults_without_autodetect():
    cfg = load_config("this-config-does-not-exist.json", use_autodetect=False)
    assert cfg.comfy_port == 8188
    assert cfg.host == "127.0.0.1"
    assert cfg.comfy_api == "http://127.0.0.1:8188"
