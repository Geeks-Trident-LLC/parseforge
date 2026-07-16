"""Turn a validated regex pattern into a canonical, kebab-case cli-name.

Fixed-text segments pass through as-is; named capture groups
(``(?P<var1>...)``) become their group name. Tokens are joined with
``-`` and lowercased, matching SPEC.md §2's naming convention.
"""

from __future__ import annotations

import re

_LEADING_FLAGS = re.compile(r"^\(\?[a-zA-Z]+\)")
_NAMED_GROUP = re.compile(r"^\(\?P<(?P<name>\w+)>.*\)$")
_ESCAPED_CHAR = re.compile(r"\\(.)")


def pattern_to_cli_name(pattern: str) -> str:
    """
    >>> pattern_to_cli_name(r"show\\s+version")
    'show-version'
    >>> pattern_to_cli_name(r"show\\s+interface\\s+(?P<var1>\\S+)\\s+status")
    'show-interface-var1-status'
    """
    body = _LEADING_FLAGS.sub("", pattern)
    tokens = [t for t in re.split(r"\\s\+", body) if t.strip()]

    parts: list[str] = []
    for token in tokens:
        token = token.strip()
        group = _NAMED_GROUP.match(token)
        if group:
            parts.append(group.group("name"))
        else:
            parts.append(_ESCAPED_CHAR.sub(r"\1", token))
    return "-".join(parts).lower()


def normalize_pattern(pattern: str) -> str:
    r"""Lowercase fixed/literal tokens in a regex pattern.

    Named-group bodies (``(?P<var1>...)``) are left untouched — they may
    contain case-sensitive regex classes like ``\S``, which lowercasing
    would silently corrupt (``\S`` -> ``\s`` is a different meaning
    entirely). Case-insensitive *matching* against a normalized pattern is
    the caller's responsibility (pass ``re.IGNORECASE``), not this
    function's — see cache.NameIndex.match and resolver.cli_name.

    >>> normalize_pattern(r"Show\s+Version")
    'show\\s+version'
    >>> normalize_pattern(r"Show\s+Interface\s+(?P<var1>\S+)\s+Status")
    'show\\s+interface\\s+(?P<var1>\\S+)\\s+status'
    """
    body = _LEADING_FLAGS.sub("", pattern)
    tokens = [t for t in re.split(r"\\s\+", body) if t.strip()]

    normalized: list[str] = []
    for token in tokens:
        token = token.strip()
        normalized.append(token if _NAMED_GROUP.match(token) else token.lower())
    return r"\s+".join(normalized)
