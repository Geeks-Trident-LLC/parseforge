"""Azure OpenAI-backed RegexBuilder implementation.

Unlike every other provider, Azure has no fixed base_url or model catalog:
the endpoint is the caller's own Azure resource, and the usual "model"
concept is replaced by an account-specific deployment name. Talks to the
``azure-ai-inference`` SDK's ``ChatCompletionsClient`` directly — not
OpenAI-compatible, not Anthropic-style, not Mistral/Cohere-style either,
though its response shape (``choices[0].message.content``,
``finish_reason``, ``usage.prompt_tokens/completion_tokens/total_tokens``)
happens to closely mirror OpenAI's.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .text import extract_pattern

if TYPE_CHECKING:
    from azure.ai.inference import ChatCompletionsClient as _ChatCompletionsClient

_DEFAULT_MAX_TOKENS = 1024

# Matches textfsm-ai's own AzureOpenAIProvider.from_env() default.
DEFAULT_API_VERSION = "2024-02-15-preview"

# HTTP statuses where retrying the exact same request can't succeed —
# mirrors providers/errors.py's NON_RETRYABLE class-name set, but the
# azure-ai-inference SDK raises a single HttpResponseError for every HTTP
# failure (status on exc.status_code, populated from the underlying HTTP
# response) rather than a family of named exception classes, so
# classification here is done by status code — same approach as Mistral/
# Cohere.
_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 409, 413, 422})


def _import_azure() -> Any:
    """Deferred import — azure-ai-inference is an optional extra
    (parseforge[azure]); nothing else in this module (or a cache-hit
    lookup, which never reaches build_pattern at all — see
    resolver.cli_name) should require it to be installed."""
    try:
        from azure.ai.inference import ChatCompletionsClient
        from azure.core.credentials import AzureKeyCredential
        from azure.core.exceptions import HttpResponseError
    except ImportError as exc:
        raise ImportError(
            "the azure-ai-inference package is required to use "
            "AzureRegexBuilder — install it via `pip install parseforge[azure]`"
        ) from exc
    return ChatCompletionsClient, AzureKeyCredential, HttpResponseError


def _build_deployment_endpoint(endpoint: str, deployment: str) -> str:
    """Normalize a base Azure resource endpoint into the full deployment
    endpoint azure-ai-inference's ChatCompletionsClient expects — mirrors
    textfsm-ai's own build_azure_endpoint(). If the caller already passed
    a full deployment endpoint, it's returned unchanged."""
    endpoint = endpoint.rstrip("/")
    if "/openai/deployments/" in endpoint:
        return endpoint
    return f"{endpoint}/openai/deployments/{deployment}"


def _is_retryable(exc: Any) -> bool:
    return getattr(exc, "status_code", None) not in _NON_RETRYABLE_STATUSES


def _format_error_reason(exc: Any) -> str:
    return f"LLM-ERROR-azure_sdk-{getattr(exc, 'status_code', None)}-{exc}"


class AzureRegexBuilder:
    """Builds a cli-name regex pattern by prompting an Azure OpenAI deployment.

    Unlike every other provider, there's no fixed model catalog — the
    ``deployment`` argument (an account-specific deployment name) is
    required, resolving from the argument if given, otherwise the
    ``AZURE_DEPLOYMENT`` environment variable. ``endpoint`` (the caller's
    own Azure resource URL) similarly resolves from the argument, then
    ``AZURE_ENDPOINT``. ``api_version`` resolves from the argument, then
    ``AZURE_API_VERSION``, then a default matching textfsm-ai's own
    AzureOpenAIProvider.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring any of these to be set for cache-hit lookups, which never
    reach the LLM at all (see resolver.cli_name).
    """

    provider = "azure"

    def __init__(
        self,
        deployment: str | None = None,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self._deployment = deployment
        self._api_key = api_key
        self._endpoint = endpoint
        self._api_version = api_version
        self._resolved_deployment: str | None = None
        self._client: _ChatCompletionsClient | None = None

    def _get_client(self) -> _ChatCompletionsClient:
        if self._client is None:
            ChatCompletionsClient, AzureKeyCredential, _ = _import_azure()
            api_key = self._api_key or os.environ.get("AZURE_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "no Azure API key — pass api_key or set AZURE_API_KEY"
                )
            endpoint = self._endpoint or os.environ.get("AZURE_ENDPOINT")
            if not endpoint:
                raise RuntimeError(
                    "no Azure endpoint — pass endpoint or set AZURE_ENDPOINT"
                )
            deployment = self._deployment or os.environ.get("AZURE_DEPLOYMENT")
            if not deployment:
                raise RuntimeError(
                    "no Azure deployment — pass deployment or set AZURE_DEPLOYMENT"
                )
            api_version = (
                self._api_version
                or os.environ.get("AZURE_API_VERSION")
                or DEFAULT_API_VERSION
            )
            self._resolved_deployment = deployment
            self._client = ChatCompletionsClient(
                endpoint=_build_deployment_endpoint(endpoint, deployment),
                credential=AzureKeyCredential(api_key),
                api_version=api_version,
            )
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        _, _, HttpResponseError = _import_azure()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS

        start = time.monotonic()
        try:
            response = self._get_client().complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                **kwargs,
            )
        except HttpResponseError as exc:
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
