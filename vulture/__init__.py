# -*- coding: utf-8 -*-
"""Vulture AI (Overlkd Studio) support package.

Currently exposes the portable configuration layer so that ``studio.py`` and
the setup scripts can share one source of truth for paths, ports and settings
instead of hard-coding ``C:\\Users\\User\\...`` / ``D:\\comfyui\\...``.

Typical use::

    from vulture.config import get_config
    cfg = get_config()
    print(cfg.comfy_dir, cfg.output_dir, cfg.comfy_api)
"""
from .config import Config, get_config, load_config

__all__ = ["Config", "get_config", "load_config"]
