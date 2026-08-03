"""Oracle Cloud Infrastructure (OCI) Generative AI-backed RegexBuilder
implementation.

Uses the native ``oci`` SDK's GenerativeAiInferenceClient.chat() Generic
chat format directly — a different SDK from every other provider, and the
most complex auth shape here: OCI signs each request cryptographically
against local config-file credentials (``~/.oci/config``, DEFAULT profile)
rather than a bearer API key or an AWS/GCP-style ambient credential chain,
and needs a THIRD app-specific parameter beyond region — ``compartment_id``
(an OCID identifying which OCI compartment/tenancy to bill and scope
requests to). Deliberately supports only the Generic chat format
(OpenAI-shaped messages/choices, used by Meta Llama and xAI Grok models on
OCI) — Cohere models are reachable through the native `cohere`/`bedrock`
providers instead, matching the same scope choice textfsm-ai's own
oci_provider.py makes.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    from oci.generative_ai_inference import GenerativeAiInferenceClient

DEFAULT_MODEL = default_model("oci")

_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TEMPERATURE = 0.2

# OCI's SDK raises a single exception class (oci.exceptions.ServiceError)
# for every failed API call, carrying an HTTP-style status code on
# exc.status — same shape as mistral/cohere/azure/gemini's own single
# error class, unlike bedrock's family of named exceptions.
_NON_RETRYABLE_STATUS_CODES = frozenset({400, 401, 403, 404, 422})


def _import_oci() -> Any:
    """Deferred import — oci is an optional extra (parseforge[oci]);
    nothing else in this module (or a cache-hit lookup, which never
    reaches build_pattern at all — see resolver.cli_name) should require
    it to be installed."""
    try:
        import oci
    except ImportError as exc:
        raise ImportError(
            "the oci package is required to use OCIRegexBuilder — "
            "install it via `pip install parseforge[oci]`"
        ) from exc
    return oci


def _is_retryable(exc: Any) -> bool:
    return getattr(exc, "status", None) not in _NON_RETRYABLE_STATUS_CODES


def _format_error_reason(exc: Any) -> str:
    status = getattr(exc, "status", "unknown")
    message = getattr(exc, "message", None) or str(exc)
    return f"LLM-ERROR-oci_sdk-{status}-{message}"


class OCIRegexBuilder:
    """Builds a cli-name regex pattern by prompting an OCI Generative AI model.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring a valid ``~/.oci/config``/``OCI_COMPARTMENT_ID``/``OCI_REGION``
    for cache-hit lookups, which never reach the LLM at all (see
    resolver.cli_name). This differs from textfsm-ai's own OCIProvider,
    which validates the OCI config file eagerly at construction time —
    that eager-validation contract doesn't fit this builder's
    lazy-construction convention (see every other provider in this
    package).

    ``compartment_id`` resolves from the constructor argument if given,
    otherwise ``OCI_COMPARTMENT_ID``. ``region`` resolves from the
    constructor argument if given, otherwise ``OCI_REGION``, otherwise
    whatever region is already set in ``~/.oci/config``. There is no
    ``api_key`` parameter at all — see the module docstring.
    """

    provider = "oci"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        compartment_id: str | None = None,
        region: str | None = None,
    ) -> None:
        self.model = model
        self._compartment_id = compartment_id
        self._region = region
        self._client: GenerativeAiInferenceClient | None = None
        self._resolved_compartment_id: str | None = None

    def _get_client(self) -> GenerativeAiInferenceClient:
        if self._client is None:
            oci_sdk = _import_oci()
            compartment_id = self._compartment_id or os.environ.get(
                "OCI_COMPARTMENT_ID"
            )
            if not compartment_id:
                raise RuntimeError(
                    "no OCI compartment ID — pass compartment_id or set "
                    "OCI_COMPARTMENT_ID"
                )
            try:
                config = oci_sdk.config.from_file()
            except Exception as exc:
                raise RuntimeError(
                    "OCI config file not found or invalid (expected "
                    f"~/.oci/config with a DEFAULT profile): {exc}"
                ) from exc
            region = self._region or os.environ.get("OCI_REGION")
            if region:
                config["region"] = region
            elif not config.get("region"):
                raise RuntimeError(
                    "no OCI region — pass region, set OCI_REGION, or set it "
                    "in ~/.oci/config"
                )
            self._resolved_compartment_id = compartment_id
            self._client = oci_sdk.generative_ai_inference.GenerativeAiInferenceClient(
                config
            )
        return self._client

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        oci_sdk = _import_oci()
        prompt = build_prompt(command, context)
        max_tokens = kwargs.pop("max_tokens", None) or _DEFAULT_MAX_TOKENS
        temperature = kwargs.pop("temperature", None)
        if temperature is None:
            temperature = _DEFAULT_TEMPERATURE

        client = self._get_client()
        models = oci_sdk.generative_ai_inference.models
        chat_details = models.ChatDetails(
            compartment_id=self._resolved_compartment_id,
            serving_mode=models.OnDemandServingMode(model_id=self.model),
            chat_request=models.GenericChatRequest(
                api_format=models.BaseChatRequest.API_FORMAT_GENERIC,
                messages=[
                    models.UserMessage(content=[models.TextContent(text=prompt)]),
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            ),
        )

        start = time.monotonic()
        try:
            response = client.chat(chat_details)
        except oci_sdk.exceptions.ServiceError as exc:
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

        chat_response = response.data.chat_response
        choice = chat_response.choices[0]
        content = "".join(
            getattr(block, "text", "") for block in choice.message.content
        )
        usage = getattr(chat_response, "usage", None)
        input_tokens = (getattr(usage, "prompt_tokens", None) or 0) if usage else 0
        output_tokens = (getattr(usage, "completion_tokens", None) or 0) if usage else 0
        total_tokens = (getattr(usage, "total_tokens", None) or 0) if usage else 0
        finish_reason = choice.finish_reason or ""

        return LLMCLIResponse(
            content=extract_pattern(content),
            raw=response.data,
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            ),
            duration_ms=duration_ms,
            reason=finish_reason,
            ready=finish_reason == "stop",
        )
