"""Loader for models.yaml — per-provider default/supported/deprecated models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_MODELS_PATH = Path(__file__).parent / "models.yaml"


def _load() -> dict[str, Any]:
    return yaml.safe_load(_MODELS_PATH.read_text(encoding="utf-8"))


def default_model(provider: str) -> str:
    return _load()[provider]["default"]


def supported_models(provider: str) -> list[str]:
    return _load()[provider]["supported"]


def deprecated_models(provider: str) -> list[str]:
    return _load()[provider].get("deprecated", [])
