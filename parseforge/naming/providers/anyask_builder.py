"""Generic RegexBuilder implementation backed by the ``anyask`` package.

Replaces 18 hand-rolled per-provider SDK integrations (anthropic.py,
azure.py, bedrock.py, ...) with a single class parameterized by
``provider``: anyask (https://github.com/Geeks-Trident-LLC/anyask) already
implements the exact same 18 vendors behind one normalized interface
(``anyask.get_provider(provider, **construction_kwargs).generate_sync(
prompt, model=..., **call_kwargs)`` -> ``AskResponse``), so there's no need
to hand-roll a client/error-classification/response-parsing dance per SDK
here anymore.

Two things anyask deliberately does NOT do, that this module still has to:

1. Retry classification -- anyask raises a flat ``ProviderError`` for every
   failed call (the original SDK exception is always attached via
   ``__cause__``). Nothing in this package retries a naming call today (see
   resolver.py), so no classification is reconstructed here either -- a
   failed call always becomes a non-``ready`` LLMCLIResponse.
2. ``finish_reason`` normalization -- anyask leaves it raw/provider-specific
   (a plain string for most vendors, a ``FinishReason`` enum member for
   Gemini/Vertex AI) precisely so callers can build their own truncation
   check. See ``_is_ready`` below.
"""

from __future__ import annotations

import time
from typing import Any

import anyask

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .models import default_model
from .text import extract_pattern

_DEFAULT_MAX_TOKENS = 1024

# Matches anyask's own AzureOpenAIProvider.__init__ fallback (confirmed by
# reading anyask/providers/azure.py) — also imported by pipeline.py/
# cli/main.py as the generation-side Azure config's own default, since
# textfsm-ai's Azure provider has no from_env()-style fallback of its own.
DEFAULT_API_VERSION = "2024-02-15-preview"

# finish_reason values (case-insensitively, after str()) that mean the
# response was cut off before completing rather than stopping naturally --
# everything else (anthropic's "end_turn", openai-family's "stop", cohere's
# "COMPLETE", gemini/vertexai's FinishReason.STOP, ...) counts as ready.
# Naming's prompt never triggers a tool-call or content-filter finish, so
# this denylist -- rather than an per-vendor allowlist of every "success"
# value -- is a safe simplification of the exact-match checks the 18
# deleted provider files each carried individually.
_TRUNCATED_FINISH_REASONS = frozenset({"length", "max_tokens", "max_output_tokens"})

# Vertex AI is the one provider where parseforge's own constructor kwarg
# name (`location`, matching its CLI flag --gcp-location) differs from
# anyask's construction-kwarg name for the same concept (`region`, reused
# from Bedrock/OCI's own "region" keyword -- see anyask/providers/
# vertexai.py). Every other provider's kwarg names already line up exactly
# (api_key, endpoint, api_version, deployment, project, region,
# compartment_id).
_CONSTRUCTION_KWARG_RENAMES: dict[str, dict[str, str]] = {
    "vertexai": {"location": "region"},
}

# deepseek-v4-flash defaults to thinking mode ON, which burns the entire
# max_tokens budget on chain-of-thought (returned separately as
# reasoning_content) and leaves nothing for the actual answer in
# `content` -- anyask's own DeepSeekProvider doesn't disable this by
# default (confirmed by reading anyask/providers/deepseek.py), so it's
# still disabled here explicitly, exactly as the old deepseek.py builder
# did. See https://api-docs.deepseek.com/guides/thinking_mode/
_DEFAULT_CALL_KWARGS: dict[str, dict[str, Any]] = {
    "deepseek": {"extra_body": {"thinking": {"type": "disabled"}}},
}


def _map_construction_kwargs(provider: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    renames = _CONSTRUCTION_KWARG_RENAMES.get(provider, {})
    mapped = {renames.get(key, key): value for key, value in kwargs.items()}
    # Drop falsy values so anyask's own env-var fallbacks (ANTHROPIC_API_KEY,
    # BEDROCK_REGION, VERTEXAI_PROJECT, ...) still apply exactly as they did
    # when the old per-provider builders left an unset kwarg as None.
    return {key: value for key, value in mapped.items() if value}


def _is_ready(finish_reason: Any) -> bool:
    if finish_reason is None:
        return False
    reason = str(getattr(finish_reason, "value", finish_reason)).lower()
    return reason not in _TRUNCATED_FINISH_REASONS


def _format_error_reason(exc: BaseException) -> str:
    cause = exc.__cause__ or exc
    return f"LLM-ERROR-{type(cause).__name__}-{cause}"


class AnyAskRegexBuilder:
    """Builds a cli-name regex pattern by prompting an LLM via ``anyask``.

    The underlying anyask ``Provider`` instance is constructed lazily, on
    the first actual call -- not in ``__init__`` -- so this can be used as
    a default RegexBuilder without requiring credentials to be set for
    cache-hit lookups, which never reach the LLM at all (see
    resolver.cli_name). Extra ``**kwargs`` passed to ``build_pattern`` (or
    a per-call ``model`` override) forward straight through to
    ``anyask``'s ``generate_sync``.
    """

    #: Set on each concrete subclass below -- an anyask/parseforge provider
    #: name, e.g. "anthropic", "azure", "bedrock".
    provider: str = ""

    def __init__(self, model: str | None = None, **kwargs: Any) -> None:
        # Azure has no fixed model catalog in models.yaml -- its
        # constructor's `deployment` kwarg stands in for a model choice
        # instead (see build_pattern's own model handling below), so no
        # default_model() lookup applies to it.
        self.model = model or (
            "" if self.provider == "azure" else default_model(self.provider)
        )
        self._construction_kwargs = _map_construction_kwargs(self.provider, kwargs)
        self._client: anyask.Provider | None = None

    def _get_client(self) -> anyask.Provider:
        if self._client is None:
            self._client = anyask.get_provider(
                self.provider, **self._construction_kwargs
            )
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS
        # Azure has no fixed model catalog -- its constructor's `deployment`
        # kwarg already fixed which deployment to call, and passing a model
        # here would just be ignored by anyask's AzureOpenAIProvider (falls
        # back to self.deployment when model is falsy), so it's left unset.
        model = kwargs.pop("model", None) or (
            None if self.provider == "azure" else self.model
        )
        for key, value in _DEFAULT_CALL_KWARGS.get(self.provider, {}).items():
            kwargs.setdefault(key, value)

        start = time.monotonic()
        try:
            response = self._get_client().generate_sync(
                prompt, model=model, max_tokens=max_tokens, **kwargs
            )
        except anyask.ProviderError as exc:
            return LLMCLIResponse(
                content="",
                raw=exc,
                usage=TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0),
                duration_ms=(time.monotonic() - start) * 1000,
                reason=_format_error_reason(exc),
                ready=False,
            )
        duration_ms = (time.monotonic() - start) * 1000

        return LLMCLIResponse(
            content=extract_pattern(response.content or ""),
            raw=response.raw,
            usage=TokenUsage(
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            ),
            duration_ms=duration_ms,
            reason=str(
                getattr(response.finish_reason, "value", response.finish_reason) or ""
            ),
            ready=_is_ready(response.finish_reason),
        )


class AnthropicRegexBuilder(AnyAskRegexBuilder):
    provider = "anthropic"


class AzureRegexBuilder(AnyAskRegexBuilder):
    provider = "azure"


class BedrockRegexBuilder(AnyAskRegexBuilder):
    provider = "bedrock"


class CerebrasRegexBuilder(AnyAskRegexBuilder):
    provider = "cerebras"


class CohereRegexBuilder(AnyAskRegexBuilder):
    provider = "cohere"


class DeepSeekRegexBuilder(AnyAskRegexBuilder):
    provider = "deepseek"


class FireworksRegexBuilder(AnyAskRegexBuilder):
    provider = "fireworks"


class GeminiRegexBuilder(AnyAskRegexBuilder):
    provider = "gemini"


class GroqRegexBuilder(AnyAskRegexBuilder):
    provider = "groq"


class MistralRegexBuilder(AnyAskRegexBuilder):
    provider = "mistral"


class MoonshotRegexBuilder(AnyAskRegexBuilder):
    provider = "moonshot"


class OCIRegexBuilder(AnyAskRegexBuilder):
    provider = "oci"


class OpenAIRegexBuilder(AnyAskRegexBuilder):
    provider = "openai"


class OpenRouterRegexBuilder(AnyAskRegexBuilder):
    provider = "openrouter"


class PerplexityRegexBuilder(AnyAskRegexBuilder):
    provider = "perplexity"


class TogetherRegexBuilder(AnyAskRegexBuilder):
    provider = "together"


class VertexAIRegexBuilder(AnyAskRegexBuilder):
    provider = "vertexai"


class XAIRegexBuilder(AnyAskRegexBuilder):
    provider = "xai"
