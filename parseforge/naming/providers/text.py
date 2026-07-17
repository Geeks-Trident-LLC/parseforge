"""Shared text-cleanup helpers for provider RegexBuilder implementations."""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"^```(?:\w+)?\s*|\s*```$")


def extract_pattern(text: str) -> str:
    """Strip markdown code fences and surrounding noise from a raw LLM reply."""
    text = _CODE_FENCE.sub("", text.strip()).strip()
    return text.splitlines()[0].strip() if text else text
