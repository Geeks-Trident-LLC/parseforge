"""Amazon Bedrock-backed RegexBuilder implementation.

Uses the native ``boto3`` bedrock-runtime Converse API directly — a
different SDK from every other provider. Unlike every provider except
Vertex AI, Bedrock has no project-level API key at all: it authenticates
via AWS's own credential chain (``AWS_ACCESS_KEY_ID``/
``AWS_SECRET_ACCESS_KEY``/``AWS_SESSION_TOKEN`` env vars,
``~/.aws/credentials``, or an IAM role) rather than a secret this builder
ever handles directly. The only Bedrock-specific parameter is
``region``, since every Bedrock call is region-scoped.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    from botocore.client import BaseClient

DEFAULT_MODEL = default_model("bedrock")

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.2

# Bedrock raises a family of named exception classes (all subclasses of
# botocore.exceptions.ClientError, dynamically generated per client, so
# they can't be referenced directly in an except clause the way
# mistral/cohere/azure/gemini's single error class can be) — classified
# here by class name, the same approach providers/errors.py uses for
# anthropic/openai's own named-exception families, since Bedrock's names
# don't line up with either of those.
_NON_RETRYABLE_EXCEPTION_NAMES = frozenset(
    {
        "ValidationException",
        "AccessDeniedException",
        "ResourceNotFoundException",
        "ConflictException",
        "ServiceQuotaExceededException",
    }
)


def _import_boto3() -> Any:
    """Deferred import — boto3 is an optional extra (parseforge[bedrock]);
    nothing else in this module (or a cache-hit lookup, which never
    reaches build_pattern at all — see resolver.cli_name) should require
    it to be installed."""
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as exc:
        raise ImportError(
            "the boto3 package is required to use BedrockRegexBuilder — "
            "install it via `pip install parseforge[bedrock]`"
        ) from exc
    return boto3, ClientError


def _is_retryable(exc: Any) -> bool:
    return type(exc).__name__ not in _NON_RETRYABLE_EXCEPTION_NAMES


def _format_error_reason(exc: Any) -> str:
    return f"LLM-ERROR-bedrock_sdk-{type(exc).__name__}-{exc}"


class BedrockRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Bedrock-hosted model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``BEDROCK_REGION``/``BEDROCK_DEFAULT_REGION`` to be set for
    cache-hit lookups, which never reach the LLM at all (see
    resolver.cli_name).

    ``region`` resolves from the constructor argument if given, otherwise
    ``BEDROCK_REGION`` then ``BEDROCK_DEFAULT_REGION`` — app-namespaced
    names, not boto3's own ``AWS_REGION``/``AWS_DEFAULT_REGION``, since
    ``region_name`` is always passed explicitly to ``boto3.client()``
    below (boto3 never gets a chance to fall back to its own env vars in
    this code path). There is no ``api_key`` parameter at all — see the
    module docstring.
    """

    provider = "bedrock"

    def __init__(self, model: str = DEFAULT_MODEL, region: str | None = None) -> None:
        self.model = model
        self._region = region
        self._client: BaseClient | None = None

    def _get_client(self) -> BaseClient:
        if self._client is None:
            boto3, _ = _import_boto3()
            region = (
                self._region
                or os.environ.get("BEDROCK_REGION")
                or os.environ.get("BEDROCK_DEFAULT_REGION")
            )
            if not region:
                raise RuntimeError(
                    "no AWS region — pass region or set BEDROCK_REGION/"
                    "BEDROCK_DEFAULT_REGION"
                )
            self._client = boto3.client("bedrock-runtime", region_name=region)
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        _, ClientError = _import_boto3()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS
        temperature = kwargs.pop("temperature", None)
        if temperature is None:
            temperature = _DEFAULT_TEMPERATURE

        start = time.monotonic()
        try:
            response = self._get_client().converse(
                modelId=self.model,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
                **kwargs,
            )
        except ClientError as exc:
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

        content_blocks = response["output"]["message"]["content"]
        text = "".join(block.get("text", "") for block in content_blocks)
        usage = response.get("usage") or {}
        input_tokens = usage.get("inputTokens") or 0
        output_tokens = usage.get("outputTokens") or 0
        total_tokens = usage.get("totalTokens") or 0
        stop_reason = response.get("stopReason") or ""

        return LLMCLIResponse(
            content=extract_pattern(text),
            raw=response,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            reason=stop_reason,
            ready=stop_reason == "end_turn",
        )
