"""Authoritative promotion and drift monitoring (SPEC.md §3.3, §5 steps 9-10)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


@dataclass(frozen=True)
class DriftStatus:
    match_rate: float
    status: str  # "ok" | "drifting" | "superseded" — see SPEC.md §6

    def breached(self, threshold: float) -> bool:
        return self.match_rate < threshold
