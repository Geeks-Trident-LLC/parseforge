"""Loader for prompts.yaml — prompt templates kept as data for easy tuning."""

from __future__ import annotations

from pathlib import Path

import yaml

_PROMPTS_PATH = Path(__file__).parent / "prompts.yaml"


def load_prompt_template(name: str) -> str:
    prompts = yaml.safe_load(_PROMPTS_PATH.read_text(encoding="utf-8"))
    return prompts[name]
