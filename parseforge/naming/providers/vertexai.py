"""Google Vertex AI-backed RegexBuilder implementation.

Reuses the SAME ``google-genai`` SDK as native Gemini — ``google.genai
.Client`` supports Vertex AI directly via ``vertexai=True, project=...,
location=...``, so no new dependency is needed. Unlike every other
provider, Vertex AI has no project-level API key at all: when no
credentials are passed, the SDK falls back to Google Cloud's Application
Default Credentials (a service account key file via
``GOOGLE_APPLICATION_CREDENTIALS``, ``gcloud auth application-default
login``, or workload identity on GCP infra) — so this builder never
handles a secret directly, only ``project``/``location``.

Vertex AI serves the SAME Gemini model catalog as the native Gemini
Developer API under identical model IDs (e.g. "gemini-2.5-flash") — the
``model``/``DEFAULT_MODEL`` handling here is unchanged from gemini.py;
only client construction (and the absence of an API key) differs.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

from ..llm import CliContext, LLMCLIResponse, TokenUsage, build_prompt
from .cost import estimate_cost
from .models import default_model
from .text import extract_pattern

if TYPE_CHECKING:
    import google.genai as genai_sdk

DEFAULT_MODEL = default_model("vertexai")

_DEFAULT_MAX_TOKENS = 1024

# HTTP statuses where retrying the exact same request can't succeed —
# mirrors providers/errors.py's NON_RETRYABLE class-name set, but the
# google-genai SDK raises a single APIError for every HTTP failure
# (status on exc.code) rather than a family of named exception classes,
# so classification here is done by status code — same approach as
# gemini.py (identical SDK, identical exception type).
_NON_RETRYABLE_STATUSES = frozenset({400, 401, 403, 404, 409, 413, 422})


def _import_genai() -> Any:
    """Deferred import — google-genai is an optional extra
    (parseforge[vertexai]); nothing else in this module (or a cache-hit
    lookup, which never reaches build_pattern at all — see
    resolver.cli_name) should require it to be installed."""
    try:
        import google.genai as genai
    except ImportError as exc:
        raise ImportError(
            "the google-genai package is required to use "
            "VertexAIRegexBuilder — install it via `pip install "
            "parseforge[vertexai]`"
        ) from exc
    return genai


def _is_retryable(exc: Any) -> bool:
    return getattr(exc, "code", None) not in _NON_RETRYABLE_STATUSES


def _format_error_reason(exc: Any) -> str:
    return f"LLM-ERROR-vertexai_sdk-{getattr(exc, 'code', None)}-{exc}"


class VertexAIRegexBuilder:
    """Builds a cli-name regex pattern by prompting a Gemini model via
    Vertex AI.

    The client is constructed lazily, on the first actual call — not in
    ``__init__`` — so this can be used as a default RegexBuilder without
    requiring ``VERTEXAI_PROJECT``/``VERTEXAI_REGION`` to be set for
    cache-hit lookups, which never reach the LLM at all (see
    resolver.cli_name).

    ``project``/``location`` resolve from the constructor arguments if
    given, otherwise the ``VERTEXAI_PROJECT``/``VERTEXAI_REGION``
    environment variables — app-namespaced names, not GCP's own
    ``GOOGLE_CLOUD_PROJECT``/``GOOGLE_CLOUD_LOCATION``, since both are
    always passed explicitly to ``genai.Client()`` below. There is no
    ``api_key`` parameter at all — see the module docstring.
    """

    provider = "vertexai"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        project: str | None = None,
        location: str | None = None,
    ) -> None:
        self.model = model
        self._project = project
        self._location = location
        self._client: genai_sdk.Client | None = None

    def _get_client(self) -> genai_sdk.Client:
        if self._client is None:
            genai = _import_genai()
            project = self._project or os.environ.get("VERTEXAI_PROJECT")
            if not project:
                raise RuntimeError(
                    "no GCP project — pass project or set VERTEXAI_PROJECT"
                )
            location = self._location or os.environ.get("VERTEXAI_REGION")
            if not location:
                raise RuntimeError(
                    "no GCP location — pass location or set VERTEXAI_REGION"
                )
            self._client = genai.Client(
                vertexai=True, project=project, location=location
            )
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
        # VertexAIProvider default; override via a thinking_budget kwarg.
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
                usage=TokenUsage(
                    input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost=0.0
                ),
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
                estimated_cost=estimate_cost(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    provider=self.provider,
                    model=self.model,
                ),
            ),
            duration_ms=duration_ms,
            # finish_reason is a str-subclassed enum whose own __str__
            # prints "FinishReason.STOP" rather than "STOP" — .value
            # keeps this consistent with every other provider's plain
            # reason strings.
            reason=finish_reason.value if finish_reason else "",
            ready=finish_reason == genai.types.FinishReason.STOP,
        )
