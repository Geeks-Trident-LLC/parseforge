"""Authoritative promotion and drift monitoring (SPEC.md §3.3, §5 steps 9-10).

Promotion runs per integration group (§6 multi-variant), not per cli-name:
each group's ``match_rate`` is its share of *all* trials for the cli-name
(``group_sample_count / total_case_count``), fed through the same
:func:`decide_promotion` used for a single-candidate case. ``reference.json``
(see :mod:`parseforge.integration`) never stores this decision — it's pure
evidence. ``total_case_count`` is always recomputed fresh from the trials on
disk rather than trusted from a prior run, so a group's promotion status can
correctly change as more trials accumulate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from parseforge import paths
from parseforge.integration import Reference, ReferenceVariant


class PromotionDecision(str, Enum):
    AUTO_PROMOTED = "auto_promoted"
    QUEUED_FOR_REVIEW = "queued_for_review"


@dataclass(frozen=True)
class PromotionGate:
    """Confidence threshold gating auto-promotion vs. human review (§3.3, §7).

    Left configurable per-project rather than hardcoded — see the open
    question in SPEC.md §7.
    """

    match_rate_threshold: float = 1.0
    min_sample_count: int = 1


def decide_promotion(
    match_rate: float, sample_count: int, gate: PromotionGate
) -> PromotionDecision:
    if (
        sample_count >= gate.min_sample_count
        and match_rate >= gate.match_rate_threshold
    ):
        return PromotionDecision.AUTO_PROMOTED
    return PromotionDecision.QUEUED_FOR_REVIEW


def total_case_count(store_root: Path, key: paths.DeviceKey) -> int:
    """Fresh count of trial run-dirs for ``key.cli_name`` — never persisted,
    always recomputed at decision time (see module docstring)."""
    trials_dir = paths.tier_path(store_root, paths.TRIALS, key)
    if not trials_dir.exists():
        return 0
    return sum(1 for d in trials_dir.iterdir() if d.is_dir())


@dataclass(frozen=True)
class GroupPromotion:
    group_id: str
    decision: PromotionDecision
    match_rate: float
    sample_count: int


def decide_group_promotions(
    reference: Reference, total_cases: int, gate: PromotionGate
) -> list[GroupPromotion]:
    """Pure decision pass: one :func:`decide_promotion` call per group."""
    results = []
    for group_id, group in reference.items():
        sample_count = group.group_case_count
        match_rate = sample_count / total_cases if total_cases else 0.0
        decision = decide_promotion(match_rate, sample_count, gate)
        results.append(
            GroupPromotion(
                group_id=group_id,
                decision=decision,
                match_rate=match_rate,
                sample_count=sample_count,
            )
        )
    return results


def _representative_variant_id(group_variants: dict[str, ReferenceVariant]) -> str:
    """Pick the variant with the highest exact_template_count, ties broken
    by lowest variant id for determinism."""
    return min(
        group_variants,
        key=lambda vid: (-group_variants[vid].exact_template_count, int(vid)),
    )


def apply_promotions(
    store_root: Path,
    key: paths.DeviceKey,
    reference: Reference,
    decisions: list[GroupPromotion],
) -> list[Path]:
    """Copy each AUTO_PROMOTED group's representative template (+ its
    originating trial's recognizers.txt) to authoritative/, and append an
    entry to promotion-log.json. QUEUED_FOR_REVIEW groups are left untouched
    — see module docstring."""
    written: list[Path] = []
    log_path = paths.authoritative_dir(store_root, key) / "promotion-log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []

    for decision in decisions:
        if decision.decision is not PromotionDecision.AUTO_PROMOTED:
            continue
        group = reference[decision.group_id]
        variant_id = _representative_variant_id(group.variants)
        variant = group.variants[variant_id]

        source_template = Path(variant.template_path)
        source_recognizers = source_template.parent / "recognizers.txt"

        dest_dir = paths.authoritative_group_dir(store_root, key, decision.group_id)
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "template.textfsm").write_text(
            source_template.read_text(encoding="utf-8"), encoding="utf-8"
        )
        if source_recognizers.exists():
            (dest_dir / "recognizers.txt").write_text(
                source_recognizers.read_text(encoding="utf-8"), encoding="utf-8"
            )
        written.append(dest_dir)

        log.append(
            {
                "group_id": decision.group_id,
                "match_rate": decision.match_rate,
                "sample_count": decision.sample_count,
                "template_source": str(source_template),
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return written


@dataclass(frozen=True)
class DriftStatus:
    match_rate: float
    status: str  # "ok" | "drifting" | "superseded" — see SPEC.md §6

    def breached(self, threshold: float) -> bool:
        return self.match_rate < threshold
