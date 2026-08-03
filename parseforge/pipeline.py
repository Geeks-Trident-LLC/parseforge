"""Pipeline orchestration (SPEC.md §4, §5) — a single trial run.

Mode 2 (loop: sample -> generate, per command) is the MVP per §4's
recommendation. Mode 1 (batch: gather-then-generate) is a config flag
that only changes the sampling stage — generation, storage, and
validation stay identical between modes.

Steps 1-7 of SPEC.md §5, wired to what each already does:
1. Input intake — the caller's responsibility (context/connection/
   provider config passed in).
2. Name resolution — :func:`parseforge.naming.resolve_cli_name`
   (LLM-backed, cached; only costs tokens on a cache miss).
3. Path resolution — :mod:`parseforge.paths` (trials/<vendor>/<family>/
   <os>/<cli-name>/<run-id>/). The OS version isn't part of the path (see
   paths.py) — it's recorded per trial in summary.json's ``command_info``.
4. Sampling — :mod:`parseforge.sampling`, written to samples/sample.txt.
   The annotated version sent to generation (see _build_sample_for_prompt)
   is built in memory only — not written to disk, since nothing reads it
   back.
5-6. Generation — :mod:`parseforge.generation`, written to derive/.
7. Self-validation — :func:`parseforge.validation.parse` runs the
   generated template against the *raw* sample (not the annotated
   prompt version) to confirm it actually parses, independent of
   whatever textfsm-ai's own pipeline already reported as ``.ready``.

Everything is written to summary.json alongside a created/ended
timestamp, duration, an ``error`` message when ``passed`` is false,
naming + generation token usage, and the generation provider/model
(the one that actually produced the template — naming's own provider
only matters on a cache miss and isn't tracked here).

Steps 8-11 (integration selection, authoritative promotion, drift
monitoring, repeat/loop) run out-of-band across all trials for a
cli-name, not per single pipeline invocation — see
:mod:`parseforge.validation` and :mod:`parseforge.promotion`.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from parseforge import generation, naming, paths, sampling, validation
from parseforge.naming.providers.azure import DEFAULT_API_VERSION


class Mode(str, Enum):
    LOOP = "loop"  # MVP: sample -> generate, per command (§4)
    BATCH = "batch"  # collect N samples per command before generation (§4)


@dataclass(frozen=True)
class LLMProviderConfig:
    """``model`` doubles as the deployment name for provider="azure" (no
    fixed model catalog there — see naming/providers/azure.py); the CLI
    resolves --deployment into this field so this dataclass and
    generation.generate()'s positional model arg stay untouched.
    ``endpoint``/``api_version`` are ignored by every provider except
    azure, and ``project``/``location`` by every provider except
    vertexai (see textfsm-ai's generation_engine.run()). ``api_key`` has
    no real value for provider="vertexai"/"bedrock"/"oci" (see
    naming/providers/vertexai.py, naming/providers/bedrock.py,
    naming/providers/oci.py) — the CLI passes an empty string there,
    which generation_engine.run() simply never reads for those
    providers.

    ``region`` is meaningful for provider="bedrock" or "oci" — it and
    ``location`` (vertexai's own region-shaped field) all ultimately
    populate run_pipeline()'s single ``region=`` kwarg (see
    run_command_pipeline() below); only one of the two fields is ever
    set for a given trial, since a trial has exactly one generation
    provider. ``compartment_id`` is only meaningful for provider="oci"
    — run_pipeline() has its own dedicated ``compartment_id=`` kwarg,
    unlike region, so it needs no such sharing/reconciliation."""

    provider: str
    api_key: str
    model: str
    endpoint: str | None = None
    api_version: str | None = None
    project: str | None = None
    location: str | None = None
    region: str | None = None
    compartment_id: str | None = None


@dataclass(frozen=True)
class TrialMetadata:
    """Optional user-supplied context about who/why this trial ran —
    recorded in summary.json, never used for path resolution."""

    project: str | None = None
    username: str | None = None
    email: str | None = None
    description: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class TrialResult:
    run_dir: Path
    cli_name: str
    passed: bool
    duration_ms: int
    total_usage: dict[str, int]


def _build_sample_for_prompt(
    sample: str, command: str, context: naming.CliContext
) -> str:
    """Annotate the raw sample with a description of its source, for
    generation's LLM prompt only — self-validation still runs against
    the unannotated ``sample`` text.

    Caveat carried over from where this format was worked out (see
    tests/real/generation/): textfsm-ai's own prompt has no
    closing delimiter on its Sample section, so this annotation isn't
    guaranteed to be excluded from what the LLM treats as data.
    """
    return (
        f"{sample}\n\n"
        "SAMPLE REFERENCE SOURCE\n"
        "=============================\n"
        f'a real "{command}" output from a '
        f"{context.vendor} {context.family} {context.os} device"
    )


def _usage_dict(usage: Any | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return asdict(usage)


def _total_usage(naming_usage: Any | None, generation_usage: Any) -> dict[str, int]:
    """Sum naming + generation usage — generation_usage is already
    accumulated across every LLM call in its own pipeline (every
    base-prompt attempt and correction-prompt retry, see textfsm-ai's
    accumulate_usage()); naming_usage is a single build_pattern() call's
    usage, or None on a cache hit (no LLM call at all)."""
    naming_input = naming_usage.input_tokens if naming_usage else 0
    naming_output = naming_usage.output_tokens if naming_usage else 0
    naming_total = naming_usage.total_tokens if naming_usage else 0
    return {
        "input_tokens": naming_input + generation_usage.input_tokens,
        "output_tokens": naming_output + generation_usage.output_tokens,
        "total_tokens": naming_total + generation_usage.total_tokens,
    }


def run_command_pipeline(
    command: str,
    context: naming.CliContext,
    connection: sampling.DeviceConnection,
    naming_builder: naming.RegexBuilder,
    sampler: sampling.Sampler,
    generation_config: LLMProviderConfig,
    *,
    store_root: Path = paths.DEFAULT_STORE_ROOT,
    naming_index_path: Path = naming.DEFAULT_INDEX_PATH,
    metadata: TrialMetadata = TrialMetadata(),
    mode: Mode = Mode.LOOP,
) -> TrialResult:
    started_at = datetime.now(timezone.utc)
    start = time.monotonic()

    # 2. Name resolution
    naming_resolution = naming.resolve_cli_name(
        command, context, builder=naming_builder, index_path=naming_index_path
    )

    # 3. Path resolution
    key = paths.DeviceKey(
        vendor=context.vendor,
        family=context.family,
        os=context.os,
        cli_name=naming_resolution.name,
    )
    run_dir = paths.trial_run_dir(store_root, key)
    samples_dir = run_dir / "samples"
    derive_dir = run_dir / "derive"
    samples_dir.mkdir(parents=True, exist_ok=True)
    derive_dir.mkdir(parents=True, exist_ok=True)

    # 4. Sampling
    sample_text = sampling.sample(sampler, connection, command)
    (samples_dir / "sample.txt").write_text(sample_text, encoding="utf-8")

    sample_for_prompt = _build_sample_for_prompt(sample_text, command, context)

    # 5-6. Generation
    gen_result = generation.generate(
        sample_for_prompt,
        generation_config.provider,
        generation_config.api_key,
        generation_config.model,
        endpoint=generation_config.endpoint or "",
        # Only meaningful for provider="azure" (ignored by every other
        # provider — see textfsm-ai's generation_engine.run()), which has
        # no from_env()-style fallback of its own on this path, unlike
        # naming/providers/azure.py's own AzureRegexBuilder — so the same
        # default is applied here explicitly.
        api_version=generation_config.api_version or DEFAULT_API_VERSION,
        project=generation_config.project or "",
        # run_pipeline()'s kwarg is named "region", not "location" (shared
        # with bedrock/oci) — location is the user-facing name (matching
        # VertexAIProvider's own constructor param and VERTEXAI_REGION's
        # naming intent), mapped here the same way --deployment maps onto
        # the positional model arg above. generation_config.region is
        # bedrock/oci's own already-correctly-named field, forwarded
        # as-is; only one of region/location is ever set for a given
        # provider.
        region=generation_config.region or generation_config.location or "",
        # Only meaningful for provider="oci" (ignored by every other
        # provider) — unlike region, run_pipeline() has a dedicated
        # compartment_id= kwarg, so no reconciliation with another field
        # is needed here.
        compartment_id=generation_config.compartment_id or "",
    )
    (derive_dir / "llm-template.textfsm").write_text(
        gen_result.raw_template, encoding="utf-8"
    )
    (derive_dir / "template.textfsm").write_text(gen_result.template, encoding="utf-8")
    (derive_dir / "readable-dsl.txt").write_text(
        gen_result.readable_dsl, encoding="utf-8"
    )
    (derive_dir / "recognizers.txt").write_text(
        "\n".join(gen_result.recognizers), encoding="utf-8"
    )

    # 7. Self-validation — against the raw sample, not the annotated one.
    parsed = validation.parse(gen_result.template, sample_text)
    self_validated = parsed.passed and bool(parsed.records)
    passed = gen_result.ready and self_validated

    error: str | None = None
    if not gen_result.ready:
        error = gen_result.reason or "generation not ready"
    elif not self_validated:
        error = (
            "; ".join(parsed.errors)
            if parsed.errors
            else "template produced no records against its own sample"
        )

    ended_at = datetime.now(timezone.utc)
    duration_ms = round((time.monotonic() - start) * 1000)

    naming_usage = (
        naming_resolution.response.usage if naming_resolution.response else None
    )
    total_usage = _total_usage(naming_usage, gen_result.usage)

    summary = {
        "created_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_ms": duration_ms,
        "passed": passed,
        "error": error,
        "metadata": asdict(metadata),
        "command_info": {
            "vendor": context.vendor,
            "family": context.family,
            "os": context.os,
            "version": context.version,
            "device_type": connection.device_type,
            "command": command,
        },
        "usage": {
            "naming": _usage_dict(naming_usage),
            "generation": _usage_dict(gen_result.usage),
            "total": total_usage,
        },
        "provider_info": {
            "provider": generation_config.provider,
            "model": generation_config.model,
        },
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )

    return TrialResult(
        run_dir=run_dir,
        cli_name=naming_resolution.name,
        passed=passed,
        duration_ms=duration_ms,
        total_usage=total_usage,
    )
