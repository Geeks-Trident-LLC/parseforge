from __future__ import annotations

import json
from pathlib import Path

from parseforge import paths
from parseforge.integration import ReferenceGroup, ReferenceVariant
from parseforge.promotion import (
    GroupPromotion,
    PromotionDecision,
    PromotionGate,
    apply_promotions,
    decide_group_promotions,
    decide_promotion,
    total_case_count,
)

KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    version="17.9.1",
    cli_name="show-clock",
)


def test_decide_promotion_auto_promotes_when_gate_cleared() -> None:
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=2)
    assert decide_promotion(0.8, 5, gate) is PromotionDecision.AUTO_PROMOTED


def test_decide_promotion_queues_when_match_rate_below_threshold() -> None:
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=2)
    assert decide_promotion(0.5, 5, gate) is PromotionDecision.QUEUED_FOR_REVIEW


def test_decide_promotion_queues_when_sample_count_below_minimum() -> None:
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=5)
    assert decide_promotion(1.0, 1, gate) is PromotionDecision.QUEUED_FOR_REVIEW


def test_total_case_count_counts_trial_run_dirs(tmp_path: Path) -> None:
    for run_id in ["20260101-000001-aaa001", "20260101-000002-aaa002"]:
        paths.trial_run_dir(tmp_path, KEY, run_id=run_id).mkdir(parents=True)

    assert total_case_count(tmp_path, KEY) == 2


def test_total_case_count_with_no_trials_dir_is_zero(tmp_path: Path) -> None:
    assert total_case_count(tmp_path, KEY) == 0


def _reference() -> dict:
    return {
        "group1": ReferenceGroup(
            keys=["LINE"],
            sample_path="sample1.txt",
            variants={"1": ReferenceVariant("t1.textfsm", 8, 8)},
        ),
        "group2": ReferenceGroup(
            keys=["DATE", "TIME"],
            sample_path="sample2.txt",
            variants={"1": ReferenceVariant("t2.textfsm", 2, 2)},
        ),
    }


def test_decide_group_promotions_scores_by_prevalence() -> None:
    reference = _reference()
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=1)

    decisions = decide_group_promotions(reference, total_cases=10, gate=gate)
    by_group = {d.group_id: d for d in decisions}

    assert by_group["group1"].match_rate == 0.8
    assert by_group["group1"].decision is PromotionDecision.AUTO_PROMOTED
    assert by_group["group2"].match_rate == 0.2
    assert by_group["group2"].decision is PromotionDecision.QUEUED_FOR_REVIEW


def test_decide_group_promotions_with_zero_total_cases_is_zero_rate() -> None:
    reference = _reference()
    gate = PromotionGate()

    decisions = decide_group_promotions(reference, total_cases=0, gate=gate)

    assert all(d.match_rate == 0.0 for d in decisions)
    assert all(d.decision is PromotionDecision.QUEUED_FOR_REVIEW for d in decisions)


def test_apply_promotions_copies_representative_variant_and_logs(
    tmp_path: Path,
) -> None:
    trial_derive = tmp_path / "trials" / "some-run" / "derive"
    trial_derive.mkdir(parents=True)
    (trial_derive / "template.textfsm").write_text("Value X (.+)\n", encoding="utf-8")
    (trial_derive / "recognizers.txt").write_text("r1\nr2", encoding="utf-8")

    other_derive = tmp_path / "trials" / "other-run" / "derive"
    other_derive.mkdir(parents=True)
    (other_derive / "template.textfsm").write_text("Value X (.+)\n", encoding="utf-8")

    reference = {
        "group1": ReferenceGroup(
            keys=["X"],
            sample_path="sample1.txt",
            variants={
                # Higher exact_template_count wins as the representative.
                "1": ReferenceVariant(str(trial_derive / "template.textfsm"), 5, 5),
                "2": ReferenceVariant(str(other_derive / "template.textfsm"), 1, 1),
            },
        ),
        "group2": ReferenceGroup(keys=["Y"], sample_path="sample2.txt", variants={}),
    }
    decisions = [
        GroupPromotion("group1", PromotionDecision.AUTO_PROMOTED, 0.9, 6),
        GroupPromotion("group2", PromotionDecision.QUEUED_FOR_REVIEW, 0.1, 1),
    ]

    written = apply_promotions(tmp_path, KEY, reference, decisions)

    expected_dir = paths.authoritative_group_dir(tmp_path, KEY, "group1")
    assert written == [expected_dir]
    assert (expected_dir / "template.textfsm").read_text(
        encoding="utf-8"
    ) == "Value X (.+)\n"
    assert (expected_dir / "recognizers.txt").read_text(encoding="utf-8") == "r1\nr2"

    # group2 (queued for review) is left untouched.
    assert not paths.authoritative_group_dir(tmp_path, KEY, "group2").exists()

    log = json.loads(
        (paths.authoritative_dir(tmp_path, KEY) / "promotion-log.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(log) == 1
    assert log[0]["group_id"] == "group1"
    assert log[0]["sample_count"] == 6


def test_apply_promotions_appends_to_existing_log(tmp_path: Path) -> None:
    trial_derive = tmp_path / "trials" / "some-run" / "derive"
    trial_derive.mkdir(parents=True)
    (trial_derive / "template.textfsm").write_text("Value X (.+)\n", encoding="utf-8")

    reference = {
        "group1": ReferenceGroup(
            keys=["X"],
            sample_path="sample1.txt",
            variants={
                "1": ReferenceVariant(str(trial_derive / "template.textfsm"), 1, 1)
            },
        ),
    }
    decisions = [GroupPromotion("group1", PromotionDecision.AUTO_PROMOTED, 1.0, 1)]

    apply_promotions(tmp_path, KEY, reference, decisions)
    apply_promotions(tmp_path, KEY, reference, decisions)

    log = json.loads(
        (paths.authoritative_dir(tmp_path, KEY) / "promotion-log.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(log) == 2
