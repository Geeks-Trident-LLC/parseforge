"""Generation stage — LLM call, extraction, cleanup, and DSL compile
(SPEC.md §5 steps 5-6), delegated to textfsm-ai's delivery pipeline
rather than reimplemented here.

textfsm-ai's run_pipeline() already covers extraction + cleanup + DSL
compilation (canonical template, readable DSL, recognizers) in one
call — see https://github.com/Geeks-Trident-LLC/textfsm-ai. Always run
in debug mode with JSON output, for full usage/timing/pipeline detail
(see GenerationResult.raw).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from textfsm_ai import run_pipeline

_SENSITIVE_KEYS = {"api_key"}


def _redact(value: Any) -> Any:
    """Strip credential-shaped fields from a parsed debug payload.

    textfsm-ai's Serializable.to_dict()/to_json() run plain
    dataclasses.asdict() — masking (mask_middle()) only happens in its
    *text*-mode output, not JSON. Debug mode's JSON embeds the raw API
    key unmasked, so it must be stripped before this result is stored
    or logged anywhere.
    """
    if isinstance(value, dict):
        return {
            k: "<redacted>" if k in _SENSITIVE_KEYS else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float


@dataclass(frozen=True)
class GenerationResult:
    """Structured result of generating + DSL-compiling a template from a sample."""

    template: str  # canonical, DSL-compiled TextFSM template
    raw_template: str  # pre-cleanup template, as the LLM returned it
    readable_dsl: str
    recognizers: list[str]
    records: list[dict[str, str]]
    usage: TokenUsage
    duration_ms: float
    ready: bool
    reason: str
    raw: dict[str, Any] = field(repr=False)


def generate(
    sample: str,
    provider: str,
    api_key: str,
    model: str,
    **kwargs: Any,
) -> GenerationResult:
    """Run textfsm-ai's full sample -> template -> DSL-compiled pipeline.

    Always runs in debug mode with JSON output (not overridable — pass
    ``mode``/``as_json`` in ``kwargs`` and this raises, same as calling
    ``run_pipeline()`` twice for the same argument would). ``**kwargs``
    forwards to ``run_pipeline()`` for everything else (``endpoint``,
    ``region``, ``max_tries``, ...).

    Never raises for a failed *generation* (a bad/truncated LLM response) —
    check ``.ready`` for that. Does raise ``ImportError`` if ``provider``'s
    SDK isn't installed (textfsm-ai's own lazy provider registry, pointing
    at the right ``pip install textfsm-ai[<provider>]`` extra) — a missing
    package is an environment problem, not a generation outcome, and is
    treated the same way here as in :mod:`parseforge.naming.providers`.
    """
    result = run_pipeline(
        sample, provider, api_key, model, mode="debug", as_json=True, **kwargs
    )
    debug = _redact(json.loads(result.output))

    usage_data = debug.get("usage") or {}
    usage = TokenUsage(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
        estimated_cost=usage_data.get("estimated_cost", 0.0),
    )

    gen_stage = (debug.get("generation_pipeline") or {}).get("last_stage") or {}
    gen_metadata = gen_stage.get("metadata") or {}

    dsl = (debug.get("dsl_pipeline") or {}).get("dsl") or {}

    return GenerationResult(
        template=dsl.get("canonical") or "",
        raw_template=dsl.get("raw_template") or gen_metadata.get("template") or "",
        readable_dsl=dsl.get("readable") or "",
        recognizers=dsl.get("recognizers") or [],
        records=gen_metadata.get("records") or [],
        usage=usage,
        duration_ms=debug.get("duration_ms", 0.0),
        ready=result.passed,
        reason=result.error,
        raw=debug,
    )
