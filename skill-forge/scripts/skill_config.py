#!/usr/bin/env python3
"""Shared config helpers for reusable skill tooling."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_CONFIG = {
    "required_frontmatter_keys": ["name", "description"],
    "allowed_frontmatter_keys": ["name", "description", "metadata", "allowed-tools", "license"],
    "required_openai_fields": ["display_name", "short_description", "default_prompt"],
    "require_openai_yaml": False,
    "require_version_file": False,
    "require_skills_index": False,
    "resource_dirs": ["references", "scripts", "assets"],
    "emit_openai_yaml": True,
    "short_description_min": 25,
    "short_description_max": 64,
    "max_name_length": 64,
    "max_description_length": 1024,
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def load_config(config_path: str | None = None) -> dict:
    config = dict(DEFAULT_CONFIG)
    if not config_path:
        return config

    path = Path(config_path).resolve()
    data = json.loads(read_text(path))
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a JSON object")
    config.update(data)
    return config
