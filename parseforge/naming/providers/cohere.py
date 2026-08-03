"""Cohere-backed RegexBuilder implementation.

Like Mistral, Cohere's official Python SDK is not built on the OpenAI
client library — it has its own generated client shape. Unlike Mistral's
single client (which exposes both complete()/complete_async() on one
object), Cohere exposes genuinely separate ``ClientV2``/``AsyncClientV2``
classes; this builder only ever needs the sync ``ClientV2``, since
``RegexBuilder.build_pattern()`` is a synchronous call.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, cast

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    import cohere as cohere_sdk

DEFAULT_MODEL = default_model("cohere")

_DEFAULT_MAX_TOKENS = 1024

# HTTP statuses where retrying the exact same request can't succeed —
# mirrors providers/errors.py's NON_RETRYABLE class-name set (BadRequest,
# Authentication, PermissionDenied, NotFound, Conflict, RequestTooLarge,
# UnprocessableEntity). The cohere SDK raises a family of named exception
# classes (BadRequestError, UnauthorizedError, ForbiddenError, ...), but
# those names don't line up with OpenAI/Anthropic's naming, and every one
# of them carries its status on exc.status_code (see
# cohere.core.api_error.ApiError, their shared base) — so classification
# here is done by status code instead of exception class name.
_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 409, 413, 422})


def _import_cohere() -> Any:
    """Deferred import — cohere is an optional extra (parseforge[cohere]);
    nothing else in this module (or a cache-hit lookup, which never reaches
    build_pattern at all — see resolver.cli_name) should require it to be
    installed."""
    try:
        import cohere
        import cohere.core.api_error  # noqa: F401  (makes cohere.core.api_error.ApiError reachable off the returned module)
    except ImportError as exc:
        raise ImportError(
            "the cohere package is required to use CohereRegexBuilder — "
            "install it via `pip install parseforge[cohere]`"
        ) from exc
    return cohere


def _status_code(exc: Any) -> int | None:
    return getattr(exc, "status_code", None)


def _is_retryable(exc: Any) -> bool:
    return _status_code(exc) not in _NON_RETRYABLE_STATUSES


def _format_error_reason(exc: Any) -> str:
    return f"LLM-ERROR-cohere_sdk-{_status_code(exc)}-{exc}"


def _extract_text(content: Any) -> str:
    """Cohere's AssistantMessageResponse.content is a list of content
    blocks (text and/or thinking blocks), unlike Mistral/OpenAI's plain
    string — join the text blocks' .text, same as textfsm-ai's own
    CohereProvider._parse_cohere_response()."""
    if isinstance(content, str):
        return content
    return "".join(getattr(block, "text", "") for block in content or [])


class CohereRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Cohere-hosted model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``COHERE_API_KEY`` to be set for cache-hit lookups, which
    never reach the LLM at all (see resolver.cli_name).

    API key resolves from the ``api_key`` argument if given, otherwise the
    ``COHERE_API_KEY`` environment variable (the SDK's own default).
    """

    provider = "cohere"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client: cohere_sdk.ClientV2 | None = None

    def _get_client(self) -> cohere_sdk.ClientV2:
        if self._client is None:
            cohere = _import_cohere()
            api_key = self._api_key or os.environ.get("COHERE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "no Cohere API key — pass api_key or set COHERE_API_KEY"
                )
            self._client = cohere.ClientV2(api_key=api_key)
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        cohere = _import_cohere()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS

        start = time.monotonic()
        try:
            response = self._get_client().chat(
                model=self.model,
                max_tokens=max_tokens,
                # cast: cohere's generated stubs want a precise
                # UserChatMessageV2/... union or matching TypedDict, but a
                # plain {"role": "user", "content": ...} dict is exactly
                # that shape.
                messages=cast(Any, [{"role": "user", "content": prompt}]),
                **kwargs,
            )
        except cohere.core.api_error.ApiError as exc:
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

        text = _extract_text(response.message.content)
        # usage/usage.tokens are both Optional, and input_tokens/
        # output_tokens are typed float — unlike every openai-compat
        # provider, Cohere's usage.tokens has no total_tokens field at
        # all, so it's computed here rather than read off the response.
        tokens = response.usage.tokens if response.usage else None
        input_tokens = int(tokens.input_tokens or 0) if tokens else 0
        output_tokens = int(tokens.output_tokens or 0) if tokens else 0
        total_tokens = input_tokens + output_tokens

        return LLMCLIResponse(
            content=extract_pattern(text),
            raw=response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            reason=response.finish_reason or "",
            ready=response.finish_reason == "COMPLETE",
        )
