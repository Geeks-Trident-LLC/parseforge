"""On-disk cli-name -> regex index, so a CLI is only ever sent to the LLM once.

Persisted as a flat JSON dict (SPEC.md naming discussion):
    {"show-version": "(?i)show\\s+version", ...}

The cli-name segment is vendor/OS-agnostic by design — vendor, family, os,
and version are already distinguishing directory levels in the storage
layout (SPEC.md §3), so a single global index is intentional rather than
one index per device context.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DEFAULT_INDEX_PATH = Path.home() / ".parseforge" / ".cli-name.json"


class NameIndex:
    """Loads, queries, and persists the cli-name -> regex mapping."""

    def __init__(self, path: Path = DEFAULT_INDEX_PATH) -> None:
        self.path = path
        self._entries: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def match(self, command: str) -> str | None:
        """Return the cli-name of the first stored pattern that fully matches
        ``command``, or None if this command hasn't been named before."""
        for cli_name, pattern in self._entries.items():
            if re.fullmatch(pattern, command):
                return cli_name
        return None

    def add(self, cli_name: str, pattern: str) -> None:
        self._entries[cli_name] = pattern

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._entries, indent=2, sort_keys=True), encoding="utf-8")
