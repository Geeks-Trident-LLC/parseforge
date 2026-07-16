"""LLM-driven regex construction for a CLI command.

Only called on a cache miss (see resolver.py) — once a command's pattern
is in the index, matching is pure regex and costs no tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .prompts import load_prompt_template

PROMPT_TEMPLATE = load_prompt_template("cli_name_regex")


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
