"""Resolve a raw CLI command to its canonical cli-name, LLM-backed with caching.

Flow:
1. Check the on-disk index (:mod:`parseforge.naming.cache`) for a stored
   pattern that already matches this command — no LLM call on a hit.
2. On a miss, ask the LLM to build a regex for it
   (:mod:`parseforge.naming.llm`). Extra ``**kwargs`` (e.g. max_tokens)
   pass through to the builder's underlying API call.
3. Reject a response that was cut off before completing (see
   LLMCLIResponse.ready) rather than trying to use a possibly-truncated
   pattern.
4. Normalize the pattern (:mod:`parseforge.naming.assemble`) — fixed/literal
   tokens lowercased, named-group bodies untouched.
5. Validate the normalized pattern actually matches its own source command,
   case-insensitively, via ``re.fullmatch(..., re.IGNORECASE)`` before
   trusting it.
6. Assemble the cli-name from the pattern and persist the new
   cli-name -> pattern entry to the index.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .assemble import normalize_pattern, pattern_to_cli_name
from .cache import DEFAULT_INDEX_PATH, NameIndex
from .llm import CliContext, RegexBuilder, UnimplementedRegexBuilder


def cli_name(
    command: str,
    context: CliContext,
    builder: RegexBuilder = UnimplementedRegexBuilder(),
    index_path: Path = DEFAULT_INDEX_PATH,
    **kwargs: Any,
) -> str:
    index = NameIndex(index_path)

    cached = index.match(command)
    if cached is not None:
        return cached

    response = builder.build_pattern(command, context, **kwargs)
    if not response.ready:
        raise ValueError(
            f"LLM response for {command!r} was not ready "
            f"(reason={response.reason!r}): {response.content!r}"
        )

    pattern = normalize_pattern(response.content)
    if not re.fullmatch(pattern, command, re.IGNORECASE):
        raise ValueError(
            f"LLM-built pattern {pattern!r} does not match its own command {command!r}"
        )

    name = pattern_to_cli_name(pattern)
    index.add(name, pattern)
    index.save()
    return name
