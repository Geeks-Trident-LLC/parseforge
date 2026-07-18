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
   <os>/<version>/<cli-name>/<run-id>/).
4. Sampling — :mod:`parseforge.sampling`, written to samples/sample.txt
   and samples/sample-for-prompt.txt (the latter with a
   "SAMPLE REFERENCE SOURCE" annotation — see _build_sample_for_prompt).
5-6. Generation — :mod:`parseforge.generation`, written to derive/.
7. Self-validation — the generated template is loaded via the real
   textfsm library and run against the *raw* sample (not the annotated
   prompt version) to confirm it actually parses.

Everything is written to summary.json alongside a created/ended
timestamp, duration, naming + generation token usage, and provider
info for both LLM calls.

Steps 8-11 (integration selection, authoritative promotion, drift
monitoring, repeat/loop) run out-of-band across all trials for a
cli-name, not per single pipeline invocation — see
:mod:`parseforge.validation` and :mod:`parseforge.promotion`.
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import textfsm

from parseforge import generation, naming, paths, sampling


class Mode(str, Enum):
    LOOP = "loop"  # MVP: sample -> generate, per command (§4)
    BATCH = "batch"  # collect N samples per command before generation (§4)


@dataclass(frozen=True)
class LLMProviderConfig:
    provider: str
    api_key: str
    model: str


@dataclass(frozen=True)
class TrialMetadata:
    """Optional user-supplied context about who/why this trial ran —
    recorded in summary.json, never used for path resolution."""

    project: str | None = None
    username: str | None = None
    user_reference: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class TrialResult:
    run_dir: Path
    cli_name: str
    passed: bool
    duration_ms: float


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


def _self_validate(template: str, sample: str) -> bool:
    """Run the generated template against its own raw sample via the
    real textfsm library (SPEC.md §5 step 7) — independent of whatever
    textfsm-ai's own pipeline already reported as .ready."""
    try:
        fsm = textfsm.TextFSM(io.StringIO(template))
        records = fsm.ParseText(sample)
    except Exception:
        return False
    return len(records) >= 1


def _usage_dict(usage: Any | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return asdict(usage)


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
        version=context.version,
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
    (samples_dir / "sample-for-prompt.txt").write_text(
        sample_for_prompt, encoding="utf-8"
    )

    # 5-6. Generation
    gen_result = generation.generate(
        sample_for_prompt,
        generation_config.provider,
        generation_config.api_key,
        generation_config.model,
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
    passed = gen_result.ready and _self_validate(gen_result.template, sample_text)

    ended_at = datetime.now(timezone.utc)
    duration_ms = (time.monotonic() - start) * 1000

    summary = {
        "created_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_ms": duration_ms,
        "passed": passed,
        "mode": mode.value,
        "metadata": asdict(metadata),
        "usage": {
            "naming_usage": _usage_dict(
                naming_resolution.response.usage if naming_resolution.response else None
            ),
            "generation_usage": _usage_dict(gen_result.usage),
        },
        "provider_info": {
            "naming": {
                "backend": type(naming_builder).__name__,
                "model": getattr(naming_builder, "model", None),
            },
            "generation": {
                "provider": generation_config.provider,
                "model": generation_config.model,
            },
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
    )
