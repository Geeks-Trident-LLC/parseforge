"""Anthropic-backed RegexBuilder implementation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .errors import format_llm_error_reason, is_retryable
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    import anthropic as anthropic_sdk

DEFAULT_MODEL = default_model("anthropic")

# Headroom in case a future/opt-in extended-thinking model burns part of
# the budget on reasoning before the actual answer — see the
# deepseek-v4-flash truncation this guards against in providers/deepseek.py.
_DEFAULT_MAX_TOKENS = 1024


def _import_anthropic() -> Any:
    """Deferred import — anthropic is an optional extra (parseforge[anthropic]);
    nothing else in this module (or a cache-hit lookup, which never reaches
    build_pattern at all — see resolver.cli_name) should require it to be
    installed."""
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "the anthropic package is required to use AnthropicRegexBuilder — "
            "install it via `pip install parseforge[anthropic]`"
        ) from exc
    return anthropic


class AnthropicRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Claude model.

    The Anthropic client is constructed lazily, on the first actual call —
    not in ``__init__`` — so this can be used as a default RegexBuilder
    without requiring ``ANTHROPIC_API_KEY`` to be set for cache-hit lookups,
    which never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``ANTHROPIC_API_KEY`` environment variable (the SDK's own default).
    """

    provider = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: anthropic_sdk.Anthropic | None = None

    def _get_client(self) -> anthropic_sdk.Anthropic:
        if self._client is None:
            anthropic = _import_anthropic()
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        anthropic = _import_anthropic()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS

        start = time.monotonic()
        try:
            response = self._get_client().messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
        except anthropic.AnthropicError as exc:
            if not is_retryable(exc):
                # Same request would fail the same way again — stop rather
                # than let a caller burn another attempt on it.
                raise
            return LLMCLIResponse(
                content="",
                raw=exc,
                usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                duration_ms=(time.monotonic() - start) * 1000,
                reason=format_llm_error_reason(exc),
                ready=False,
            )
        duration_ms = (time.monotonic() - start) * 1000

        text = "".join(block.text for block in response.content if block.type == "text")
        # Anthropic's API has no total field of its own — sum it, unlike
        # DeepSeek/OpenAI-compatible responses, which supply total_tokens
        # directly and may account for it differently (e.g. cached-token
        # pricing) than a simple input+output sum.
        total_tokens = response.usage.input_tokens + response.usage.output_tokens
        return LLMCLIResponse(
            content=extract_pattern(text),
            raw=response,
            usage=TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            reason=response.stop_reason or "",
            ready=response.stop_reason == "end_turn",
        )
