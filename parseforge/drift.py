"""Drift monitoring (SPEC.md §5 step 10, §3.3).

Checks an already-authoritative template against a new production sample,
logs the result to that cli-name's ``drift-log.json``, and — on breach —
writes the failing sample into ``trials/.../<cli-name>/`` as a new run, so
it re-enters the pipeline at generation (§5 step 4) and can work its way
back through ``integration/`` toward a possible replacement authoritative
version, instead of drift being a one-off alert.

A cli-name can hold multiple simultaneously-valid authoritative variants
(§6 — ``template.textfsm``, ``template-v2.textfsm``, ...); drift is
tracked per variant, identified by the same ``suffix`` promotion.py used
to write it (``None`` for the unsuffixed "current version"), not merged
across variants, since each one independently serves production traffic.
Match rate is a rolling rate over the trailing ``window`` checks for that
variant — a single check is only ever one data point, not the whole
picture drift is meant to catch.

Requeuing only seeds ``trials/`` with the raw failing sample — it
deliberately does not call :mod:`parseforge.generation` itself (that
needs a live provider/API key, the same credential this project has no
way to supply automatically; see :mod:`parseforge.pipeline`). A requeued
run has no ``summary.json`` yet, so :func:`parseforge.integration._trial_passed`
correctly ignores it until a real pipeline run finishes it.

SPEC.md §6 also describes a third status, ``superseded`` (a drifting
variant that already has a replacement in flight) — left out here since
setting it requires promotion.py to know about drift-log.json entries at
write time, which is a promotion.py change, not a drift.py one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from parseforge import paths, validation


@dataclass(frozen=True)
class DriftGate:
    match_rate_threshold: float = 1.0
    window: int = 20


@dataclass(frozen=True)
class DriftCheckResult:
    case_key: str
    suffix: str | None
    passed: bool
    match_rate: float
    status: str  # "ok" | "drifting"
    checked_at: str
    requeued_to: str | None


def _template_path(store_root: Path, key: paths.DeviceKey, suffix: str | None) -> Path:
    suffix_part = f"-{suffix}" if suffix else ""
    return paths.authoritative_dir(store_root, key) / f"template{suffix_part}.textfsm"


def _requeue_failing_sample(
    store_root: Path, key: paths.DeviceKey, sample_text: str
) -> Path:
    """Write a failing production sample into trials/ as a new run (§5
    step 10) so it's ready for generation to pick up, same shape sampling
    would have produced (samples/sample.txt) minus summary.json, since no
    template has been generated for it yet."""
    run_dir = paths.trial_run_dir(store_root, key)
    samples_dir = run_dir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    (samples_dir / "sample.txt").write_text(sample_text, encoding="utf-8")
    return run_dir


def check_drift(
    store_root: Path,
    key: paths.DeviceKey,
    sample_text: str,
    *,
    suffix: str | None = None,
    gate: DriftGate = DriftGate(),
) -> DriftCheckResult:
    """Run the authoritative template for ``(key, suffix)`` against a new
    production sample, append the result to that cli-name's
    ``drift-log.json``, and return the rolling match rate + status. On
    breach, requeues ``sample_text`` into ``trials/`` as a new run.

    Raises ``FileNotFoundError`` if that variant has never been promoted —
    there's nothing to check drift against.
    """
    template_path = _template_path(store_root, key, suffix)
    if not template_path.exists():
        raise FileNotFoundError(
            f"no authoritative template at {template_path} — nothing to "
            "check drift against"
        )
    template_text = template_path.read_text(encoding="utf-8")
    parsed = validation.parse(template_text, sample_text)
    passed = parsed.passed and bool(parsed.records)

    case_key = key.relative_path().as_posix()
    log_path = paths.drift_log_path(store_root, key)
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []

    prior_for_variant = [entry for entry in log if entry.get("suffix") == suffix]
    window = prior_for_variant[-(gate.window - 1) :] if gate.window > 1 else []
    window_passed = [entry["passed"] for entry in window] + [passed]
    match_rate = sum(window_passed) / len(window_passed)
    status = "ok" if match_rate >= gate.match_rate_threshold else "drifting"

    requeued_to: Path | None = None
    if not passed:
        requeued_to = _requeue_failing_sample(store_root, key, sample_text)

    checked_at = datetime.now(timezone.utc).isoformat()
    log.append(
        {
            "case": case_key,
            "suffix": suffix,
            "passed": passed,
            "match_rate": match_rate,
            "status": status,
            "checked_at": checked_at,
            "requeued_to": str(requeued_to) if requeued_to else None,
        }
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")

    return DriftCheckResult(
        case_key=case_key,
        suffix=suffix,
        passed=passed,
        match_rate=match_rate,
        status=status,
        checked_at=checked_at,
        requeued_to=str(requeued_to) if requeued_to else None,
    )
