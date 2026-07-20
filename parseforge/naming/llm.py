"""LLM-driven regex construction for a CLI command.

Only called on a cache miss (see resolver.py) — once a command's pattern
is in the index, matching is pure regex and costs no tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float


@dataclass(frozen=True)
class LLMCLIResponse:
    """Structured result of a single build_pattern() call.

    ``content`` is the extracted, cleaned pattern text (see
    providers.text.extract_pattern) — what callers actually want.
    ``raw`` is the untouched SDK response object, kept for
    debugging/auditing (mirrors SPEC.md's raw-llm-response.txt /
    usage.txt trial artifacts for a future generation pipeline).
    ``ready`` is False when the response was cut off before completing
    (e.g. hit max_tokens) rather than stopping naturally — resolver.py
    treats a non-ready response as an error rather than trying to use a
    possibly-truncated pattern.
    """

    content: str
    raw: Any
    usage: TokenUsage
    duration_ms: float
    reason: str
    ready: bool


class RegexBuilder(Protocol):
    """An LLM backend that turns a raw CLI command into a regex pattern.

    Extra ``**kwargs`` (e.g. ``max_tokens``, provider-specific request
    options) are passed through to the underlying API call, letting a
    caller override a builder's defaults per-call without subclassing it.
    """

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse: ...


class UnimplementedRegexBuilder:
    """Default RegexBuilder — no LLM client is wired into the scaffold yet."""

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        raise NotImplementedError(
            "no RegexBuilder configured — wire an LLM client that sends "
            "build_prompt(command, context) and returns an LLMCLIResponse"
        )
