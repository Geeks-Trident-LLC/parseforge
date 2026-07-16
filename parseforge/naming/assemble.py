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
    >>> pattern_to_cli_name(r"(?i)show\\s+version")
    'show-version'
    >>> pattern_to_cli_name(r"(?i)show\\s+interface\\s+(?P<var1>\\S+)\\s+status")
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
