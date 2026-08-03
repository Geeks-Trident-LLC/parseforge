"""Google Gemini-backed RegexBuilder implementation.

Like Mistral/Cohere/Azure, Gemini's official Python SDK (``google-genai``)
is not built on the OpenAI client library — it has its own client shape
(``client.models.generate_content()``). Talks to the SDK directly.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    import google.genai as genai_sdk

DEFAULT_MODEL = default_model("gemini")

_DEFAULT_MAX_TOKENS = 1024

# HTTP statuses where retrying the exact same request can't succeed —
# mirrors providers/errors.py's NON_RETRYABLE class-name set, but the
# google-genai SDK raises a single APIError for every HTTP failure
# (status on exc.code) rather than a family of named exception classes,
# so classification here is done by status code — same approach as
# Mistral/Cohere/Azure.
_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 409, 413, 422})


def _import_genai() -> Any:
    """Deferred import — google-genai is an optional extra
    (parseforge[gemini]); nothing else in this module (or a cache-hit
    lookup, which never reaches build_pattern at all — see
    resolver.cli_name) should require it to be installed."""
    try:
        import google.genai as genai
    except ImportError as exc:
        raise ImportError(
            "the google-genai package is required to use GeminiRegexBuilder — "
            "install it via `pip install parseforge[gemini]`"
        ) from exc
    return genai


def _is_retryable(exc: Any) -> bool:
    return getattr(exc, "code", None) not in _NON_RETRYABLE_STATUSES


def _format_error_reason(exc: Any) -> str:
    return f"LLM-ERROR-gemini_sdk-{getattr(exc, 'code', None)}-{exc}"


class GeminiRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Gemini model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``GEMINI_API_KEY`` to be set for cache-hit lookups, which
    never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``GEMINI_API_KEY`` environment variable (the SDK's own default).
    """

    provider = "gemini"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: genai_sdk.Client | None = None

    def _get_client(self) -> genai_sdk.Client:
        if self._client is None:
            genai = _import_genai()
            api_key = self._api_key or os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "no Gemini API key — pass api_key or set GEMINI_API_KEY"
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        genai = _import_genai()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS
        temperature = kwargs.pop("temperature", None)
        # Disabled by default (budget 0) — thinking mode adds latency/
        # cost this naming call doesn't need, matching textfsm-ai's own
        # GeminiProvider default; override via a thinking_budget kwarg.
        thinking_budget = kwargs.pop("thinking_budget", 0)

        start = time.monotonic()
        try:
            response = self._get_client().models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                    thinking_config=genai.types.ThinkingConfig(
                        thinking_budget=thinking_budget
                    ),
                    **kwargs,
                ),
            )
        except genai.errors.APIError as exc:
            if not _is_retryable(exc):
                # Same request would fail the same way again — stop rather
                # than let a caller burn another attempt on it.
                raise
            return LLMCLIResponse(
                content="",
                raw=exc,
                usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                duration_ms=(time.monotonic() - start) * 1000,
                reason=_format_error_reason(exc),
                ready=False,
            )
        duration_ms = (time.monotonic() - start) * 1000

        candidate = response.candidates[0] if response.candidates else None
        finish_reason = candidate.finish_reason if candidate else None
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage else 0
        output_tokens = (usage.candidates_token_count or 0) if usage else 0
        total_tokens = (usage.total_token_count or 0) if usage else 0

        return LLMCLIResponse(
            content=extract_pattern(response.text or ""),
            raw=response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            # finish_reason is a str-subclassed enum whose own __str__
            # prints "FinishReason.STOP" rather than "STOP" — .value
            # keeps this consistent with every other provider's plain
            # lowercase/uppercase reason strings.
            reason=finish_reason.value if finish_reason else "",
            ready=finish_reason == genai.types.FinishReason.STOP,
        )
