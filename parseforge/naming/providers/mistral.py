"""Mistral AI-backed RegexBuilder implementation.

Unlike the OpenAI-compatible providers (DeepSeek/Groq/xAI/Together/
Fireworks/Perplexity/OpenRouter/Moonshot/Cerebras), Mistral's official
Python SDK is not built on the OpenAI client library — it has its own
generated client shape (``client.chat.complete()``), even though the
underlying response shape (``choices[0].message.content``,
``usage.prompt_tokens/completion_tokens/total_tokens``) closely mirrors
OpenAI's chat-completions format. So this talks to the native
``mistralai`` SDK directly rather than pointing the ``openai`` SDK at a
different base_url.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, cast

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    import mistralai as mistralai_sdk

DEFAULT_MODEL = default_model("mistral")

_DEFAULT_MAX_TOKENS = 1024

# HTTP statuses where retrying the exact same request can't succeed —
# mirrors providers/errors.py's NON_RETRYABLE class-name set (BadRequest,
# Authentication, PermissionDenied, NotFound, Conflict, RequestTooLarge,
# UnprocessableEntity), but the mistralai SDK raises a single SDKError for
# every HTTP failure (status carried on exc.raw_response.status_code)
# rather than a family of named exception classes, so classification here
# is done by status code instead of exception class name.
_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 409, 413, 422})


def _import_mistralai() -> Any:
    """Deferred import — mistralai is an optional extra (parseforge[mistral]);
    nothing else in this module (or a cache-hit lookup, which never reaches
    build_pattern at all — see resolver.cli_name) should require it to be
    installed."""
    try:
        import mistralai
    except ImportError as exc:
        raise ImportError(
            "the mistralai package is required to use MistralRegexBuilder — "
            "install it via `pip install parseforge[mistral]`"
        ) from exc
    return mistralai


def _status_code(exc: Any) -> int | None:
    return getattr(getattr(exc, "raw_response", None), "status_code", None)


def _is_retryable(exc: Any) -> bool:
    return _status_code(exc) not in _NON_RETRYABLE_STATUSES


def _format_error_reason(exc: Any) -> str:
    return f"LLM-ERROR-mistral_sdk-{_status_code(exc)}-{exc}"


class MistralRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Mistral-hosted model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``MISTRAL_API_KEY`` to be set for cache-hit lookups, which
    never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``MISTRAL_API_KEY`` environment variable (the SDK's own default).
    """

    provider = "mistral"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: mistralai_sdk.Mistral | None = None

    def _get_client(self) -> mistralai_sdk.Mistral:
        if self._client is None:
            mistralai = _import_mistralai()
            api_key = self._api_key or os.environ.get("MISTRAL_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "no Mistral API key — pass api_key or set MISTRAL_API_KEY"
                )
            self._client = mistralai.Mistral(api_key=api_key)
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        mistralai = _import_mistralai()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS

        start = time.monotonic()
        try:
            response = self._get_client().chat.complete(
                model=self.model,
                max_tokens=max_tokens,
                # cast: mistralai's generated stubs want a precise
                # AssistantMessage/SystemMessage/... union or matching
                # TypedDict, but a plain {"role": "user", "content": ...}
                # dict is exactly the shape UserMessageTypedDict expects.
                messages=cast(Any, [{"role": "user", "content": prompt}]),
                **kwargs,
            )
        except mistralai.models.SDKError as exc:
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

        choice = response.choices[0]
        content = choice.message.content
        text = content if isinstance(content, str) else ""
        # prompt_tokens/completion_tokens/total_tokens are typed
        # Optional[int] = 0 in Mistral's UsageInfo, even though the API
        # always populates them — guard against the type, not just the
        # runtime default.
        input_tokens = response.usage.prompt_tokens or 0
        output_tokens = response.usage.completion_tokens or 0
        total_tokens = response.usage.total_tokens or 0
        return LLMCLIResponse(
            content=extract_pattern(text),
            raw=response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            reason=choice.finish_reason or "",
            ready=choice.finish_reason == "stop",
        )
