"""Resolve a raw CLI command to its canonical cli-name, LLM-backed with caching.

Flow:
1. Check the on-disk index (:mod:`parseforge.naming.cache`) for a stored
   pattern that already matches this command — no LLM call on a hit.
2. On a miss, ask the LLM to build a regex for it
   (:mod:`parseforge.naming.llm`).
3. Normalize the pattern (:mod:`parseforge.naming.assemble`) — fixed/literal
   tokens lowercased, named-group bodies untouched.
4. Validate the normalized pattern actually matches its own source command,
   case-insensitively, via ``re.fullmatch(..., re.IGNORECASE)`` before
   trusting it.
5. Assemble the cli-name from the pattern and persist the new
   cli-name -> pattern entry to the index.
"""

from __future__ import annotations

import re
from pathlib import Path

from .assemble import normalize_pattern, pattern_to_cli_name
from .cache import DEFAULT_INDEX_PATH, NameIndex
from .llm import CliContext, RegexBuilder, UnimplementedRegexBuilder


def cli_name(
    command: str,
    context: CliContext,
    builder: RegexBuilder = UnimplementedRegexBuilder(),
    index_path: Path = DEFAULT_INDEX_PATH,
) -> str:
    index = NameIndex(index_path)

    cached = index.match(command)
    if cached is not None:
        return cached

    pattern = normalize_pattern(builder.build_pattern(command, context))
    if not re.fullmatch(pattern, command, re.IGNORECASE):
        raise ValueError(
            f"LLM-built pattern {pattern!r} does not match its own command {command!r}"
        )

    name = pattern_to_cli_name(pattern)
    index.add(name, pattern)
    index.save()
    return name
