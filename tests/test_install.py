# -*- coding: utf-8 -*-
"""Installer helpers: presence detection must not count leftovers as installed."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "setup"))
import install  # noqa: E402


def test_node_core_matches_renamed_forks():
    assert install._node_core("comfyui-reactor-node") == install._node_core("ComfyUI-ReActor")


def test_is_present_missing_path():
    assert not install.is_present({}, os.path.join("nope", "never", "here"))


def test_is_present_small_file(tmp_path):
    f = tmp_path / "tiny.safetensors"
    f.write_bytes(b"x" * 10)
    assert not install.is_present({}, str(f))


def test_is_present_big_file(tmp_path):
    f = tmp_path / "model.safetensors"
    f.write_bytes(b"x" * 2_000_000)
    assert install.is_present({}, str(f))


def test_is_present_dir_ignores_hf_cache_leftover(tmp_path):
    # An interrupted snapshot download leaves only .cache behind -- that must
    # NOT count as installed, or the model is skipped forever on re-runs.
    d = tmp_path / "liveportrait"
    (d / ".cache").mkdir(parents=True)
    (d / ".cache" / "partial.bin").write_bytes(b"x" * 2_000_000)
    assert not install.is_present({}, str(d))
    (d / "weights.safetensors").write_bytes(b"x" * 2_000_000)
    assert install.is_present({}, str(d))


def test_default_chat_model_prefers_manifest_default():
    manifest = {"models": [
        {"source": {"type": "ollama"}, "target_relative_path": "a:1b",
         "chat_profile": {"name": "Fast", "order": 2}},
        {"source": {"type": "ollama"}, "target_relative_path": "b:3b",
         "chat_profile": {"name": "Super Fast", "order": 1, "default": True}},
    ]}
    cfg = install.load_config("this-config-does-not-exist.json", use_autodetect=False)
    assert install._default_chat_model(manifest, cfg) == "b:3b"
