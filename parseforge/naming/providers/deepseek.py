"""DeepSeek-backed RegexBuilder implementation.

DeepSeek's API mirrors OpenAI's chat.completions surface (same request/
response format), so this uses the `openai` SDK pointed at DeepSeek's
base URL rather than a dedicated DeepSeek client.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .errors import format_llm_error_reason, is_retryable
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    import openai as openai_sdk

DEFAULT_MODEL = default_model("deepseek")

_BASE_URL = "https://api.deepseek.com"

_DEFAULT_MAX_TOKENS = 1024

# deepseek-v4-flash defaults to thinking mode ON, which burns the entire
# max_tokens budget on chain-of-thought (returned separately as
# reasoning_content) and leaves nothing for the actual answer in
# `content` — a trivial one-line regex task doesn't need reasoning at
# all, so it's disabled explicitly by default. See:
# https://api-docs.deepseek.com/guides/thinking_mode/
_THINKING_DISABLED = {"thinking": {"type": "disabled"}}


def _import_openai() -> Any:
    """Deferred import — openai is an optional extra (parseforge[deepseek]);
    nothing else in this module (or a cache-hit lookup, which never reaches
    build_pattern at all — see resolver.cli_name) should require it to be
    installed."""
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "the openai package is required to use DeepSeekRegexBuilder — "
            "install it via `pip install parseforge[deepseek]`"
        ) from exc
    return openai


class DeepSeekRegexBuilder:
    """Builds a cli-name regex pattern by prompting a DeepSeek model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``DEEPSEEK_API_KEY`` to be set for cache-hit lookups, which
    never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``DEEPSEEK_API_KEY`` environment variable (unlike Anthropic/OpenAI's
    SDKs, the ``openai`` package has no built-in notion of DeepSeek's key,
    so this is resolved explicitly rather than left to the SDK).
    """

    provider = "deepseek"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: openai_sdk.OpenAI | None = None

    def _get_client(self) -> openai_sdk.OpenAI:
        if self._client is None:
            openai = _import_openai()
            api_key = self._api_key or os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "no DeepSeek API key — pass api_key or set DEEPSEEK_API_KEY"
                )
            self._client = openai.OpenAI(api_key=api_key, base_url=_BASE_URL)
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        openai = _import_openai()
        prompt = build_prompt(command, context)
        # Callers can override either of these per-call (e.g. re-enable
        # thinking mode, raise max_tokens further); anything else in
        # kwargs — temperature, top_p, etc. — passes through untouched.
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS
        extra_body = kwargs.pop("extra_body", None) or _THINKING_DISABLED

        start = time.monotonic()
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                extra_body=extra_body,
                **kwargs,
            )
        except openai.OpenAIError as exc:
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

        choice = response.choices[0]
        return LLMCLIResponse(
            content=extract_pattern(choice.message.content or ""),
            raw=response,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            duration_ms=duration_ms,
            reason=choice.finish_reason or "",
            ready=choice.finish_reason == "stop",
        )
