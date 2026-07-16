"""LLM-driven regex construction for a CLI command.

Only called on a cache miss (see resolver.py) — once a command's pattern
is in the index, matching is pure regex and costs no tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

PROMPT_TEMPLATE = """\
You are converting one network device CLI command into a regex pattern.

=== DEVICE CONTEXT (reference only) ===
Vendor: {vendor}
Family: {family}
OS: {os}
OS version: {version}
This context tells you what kind of device the command below runs on.
Do NOT include any of it in the regex. Do NOT build a regex for it.

=== COMMAND TO CONVERT ===
{command}

Build a regex that matches ONLY the command in the COMMAND TO CONVERT \
section above, and nothing else:
- If a token is fixed text, use it as-is and then convert to lower case.
- If a token is variable text, use a regex to match it, and name the \
capture group var1, var2, ... in left-to-right order of appearance.
- Use \\s+ to match whitespace between tokens.
- The vendor, family, OS, and version from the context above are never part \
of the command and must never appear in the regex.

Example 1: command is "show version" -> "show" and "version" are fixed \
text -> "show\\s+version"

Example 2: command is "show interface Ge1.1 status" -> "show", \
"interface", and "status" are fixed text -> \
"show\\s+interface\\s+(?P<var1>\\S+)\\s+status"

Respond with only the regex pattern, nothing else.
"""


@dataclass(frozen=True)
class CliContext:
    vendor: str
    family: str
    os: str
    version: str


def build_prompt(command: str, context: CliContext) -> str:
    return PROMPT_TEMPLATE.format(
        command=command,
        vendor=context.vendor,
        family=context.family,
        os=context.os,
        version=context.version,
    )


class RegexBuilder(Protocol):
    """An LLM backend that turns a raw CLI command into a regex pattern."""

    def build_pattern(self, command: str, context: CliContext) -> str: ...


class UnimplementedRegexBuilder:
    """Default RegexBuilder — no LLM client is wired into the scaffold yet."""

    def build_pattern(self, command: str, context: CliContext) -> str:
        raise NotImplementedError(
            "no RegexBuilder configured — wire an LLM client that sends "
            "build_prompt(command, context) and returns the regex pattern"
        )
