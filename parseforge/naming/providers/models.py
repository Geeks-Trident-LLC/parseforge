"""Loader for models.yaml — per-provider default model ID."""

from __future__ import annotations

from pathlib import Path

import yaml

_MODELS_PATH = Path(__file__).parent / "models.yaml"


def _load() -> dict[str, str]:
    return yaml.safe_load(_MODELS_PATH.read_text(encoding="utf-8"))


def default_model(provider: str) -> str:
    return _load()[provider]
