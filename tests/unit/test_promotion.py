from __future__ import annotations

import hashlib
import json
from pathlib import Path

from parseforge import paths
from parseforge.integration import ReferenceGroup, ReferenceVariant
from parseforge.promotion import (
    GroupEvaluation,
    PromotionDecision,
    PromotionGate,
    PromotionMetadata,
    PromotionRunResult,
    UserReviewedRequest,
    decide_promotion,
    evaluate_cases,
    promote_auto,
    promote_user_reviewed,
)

KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    cli_name="show-clock",
)
OTHER_KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    cli_name="show-version",
)

_TEMPLATE = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"
_TEMPLATE_LINE_VARIANT = "Value LINE (\\S.*)\n\nStart\n  ^${LINE} -> Record\n"
_TEMPLATE_B = (
    "Value DATE (\\S+)\nValue TIME (\\S+)\n\nStart\n  ^${DATE}\\s+${TIME} -> Record\n"
)


def _write_trial(
    store_root: Path,
    run_id: str,
    template: str,
    sample: str,
    key: paths.DeviceKey = KEY,
    passed: bool = True,
    recognizers: str = "r1\nr2",
) -> Path:
    run_dir = paths.trial_run_dir(store_root, key, run_id=run_id)
    (run_dir / "derive").mkdir(parents=True, exist_ok=True)
    (run_dir / "samples").mkdir(parents=True, exist_ok=True)
    (run_dir / "derive" / "template.textfsm").write_text(template, encoding="utf-8")
    (run_dir / "derive" / "recognizers.txt").write_text(recognizers, encoding="utf-8")
    (run_dir / "samples" / "sample.txt").write_text(sample, encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"passed": passed}), encoding="utf-8"
    )
    return run_dir


def test_decide_promotion_auto_promotes_when_gate_cleared() -> None:
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=2)
    assert decide_promotion(0.8, 5, gate) is PromotionDecision.AUTO_PROMOTED


def test_decide_promotion_queues_when_match_rate_below_threshold() -> None:
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=2)
    assert decide_promotion(0.5, 5, gate) is PromotionDecision.QUEUED_FOR_REVIEW


def test_decide_promotion_queues_when_sample_count_below_minimum() -> None:
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=5)
    assert decide_promotion(1.0, 1, gate) is PromotionDecision.QUEUED_FOR_REVIEW


def _fake_reference() -> dict[str, ReferenceGroup]:
    return {
        "group1": ReferenceGroup(
            keys=["LINE"],
            sample_path="s1.txt",
            variants={"1": ReferenceVariant("t1.textfsm", 8, 8)},
        ),
    }


def test_evaluate_cases_applies_default_gate() -> None:
    references = {"case-a": _fake_reference()}
    summary = {
        "cases": {
            "case-a": {"groups": {"group1": {"case_count": 8, "ratio_of_passed": 0.8}}}
        }
    }
    gate = PromotionGate(match_rate_threshold=0.7, min_sample_count=1)

    evaluations = evaluate_cases(references, summary, gate)

    assert evaluations == [
        GroupEvaluation("case-a", "group1", PromotionDecision.AUTO_PROMOTED, 0.8, 8)
    ]


def test_evaluate_cases_uses_per_case_gate_override() -> None:
    references = {"case-a": _fake_reference()}
    summary = {
        "cases": {
            "case-a": {"groups": {"group1": {"case_count": 8, "ratio_of_passed": 0.8}}}
        }
    }
    default_gate = PromotionGate(match_rate_threshold=0.9, min_sample_count=1)
    override = PromotionGate(match_rate_threshold=0.7, min_sample_count=1)

    evaluations = evaluate_cases(
        references, summary, default_gate, case_gates={"case-a": override}
    )

    assert evaluations[0].decision is PromotionDecision.AUTO_PROMOTED


def test_evaluate_cases_only_cases_filters() -> None:
    references = {"case-a": _fake_reference(), "case-b": _fake_reference()}
    summary = {
        "cases": {
            "case-a": {"groups": {"group1": {"case_count": 8, "ratio_of_passed": 1.0}}},
            "case-b": {"groups": {"group1": {"case_count": 8, "ratio_of_passed": 1.0}}},
        }
    }

    evaluations = evaluate_cases(
        references, summary, PromotionGate(), only_cases={"case-a"}
    )

    assert {e.case_key for e in evaluations} == {"case-a"}


def test_promote_auto_with_no_trials_returns_empty_result(tmp_path: Path) -> None:
    result = promote_auto(tmp_path, PromotionMetadata(user="tuyen"))

    assert result == PromotionRunResult(
        promoted=[], unqualified=[], unmatched_cases=[], invalid_requests=[]
    )


def test_promote_auto_promotes_qualifying_group_and_reports_unqualified(
    tmp_path: Path,
) -> None:
    # KEY's case: two passed trials, identical schema/template -> group1's
    # ratio_of_passed is 1.0, clearing the default gate.
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    _write_trial(tmp_path, "20260101-000002-aaa002", _TEMPLATE, "goodbye world\n")

    # OTHER_KEY's case: two passed trials with two different schemas -> two
    # groups, each with ratio_of_passed 0.5 -- neither clears the default
    # 1.0 threshold, so both are reported unqualified.
    _write_trial(
        tmp_path, "20260101-000001-bbb001", _TEMPLATE, "hello world\n", key=OTHER_KEY
    )
    _write_trial(
        tmp_path,
        "20260101-000002-bbb002",
        _TEMPLATE_B,
        "2024-01-01 10:00:00\n",
        key=OTHER_KEY,
    )

    metadata = PromotionMetadata(user="tuyen", email="tuyen@example.com")
    result = promote_auto(tmp_path, metadata)

    assert len(result.promoted) == 1
    template_path = result.promoted[0]
    dest_dir = paths.authoritative_dir(tmp_path, KEY)
    # group1 is the primary/unsuffixed variant -- no group directory, no
    # suffix, sitting directly in the flat cli-name directory.
    assert template_path == dest_dir / "template.textfsm"
    assert template_path.read_text(encoding="utf-8") == _TEMPLATE
    assert (dest_dir / "recognizers.txt").read_text(encoding="utf-8") == "r1\nr2"

    data_dir = paths.promoted_data_dir(tmp_path, KEY)
    assert (data_dir / "sample.txt").exists()
    records = json.loads((data_dir / "records.json").read_text(encoding="utf-8"))
    assert records

    golden_hash = (dest_dir / "golden.hash").read_text(encoding="utf-8")
    expected_hash = hashlib.sha256(template_path.read_bytes()).hexdigest()
    assert golden_hash == expected_hash

    artifact = json.loads((dest_dir / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["created_by"] == "tuyen"
    assert artifact["email"] == "tuyen@example.com"
    assert artifact["mode"] == "auto_promoted"
    assert artifact["suffix"] is None
    assert artifact["case"] == "cisco/catalyst9200/ios-xe/show-clock"

    log = json.loads(paths.authoritative_log_path(tmp_path).read_text(encoding="utf-8"))
    assert len(log) == 1
    assert log[0]["case"] == "cisco/catalyst9200/ios-xe/show-clock"
    assert log[0]["group_id"] == "group1"
    assert log[0]["mode"] == "auto_promoted"

    assert len(result.unqualified) == 2
    assert {e.case_key for e in result.unqualified} == {
        "cisco/catalyst9200/ios-xe/show-version"
    }
    assert result.unmatched_cases == []

    summary = json.loads(
        paths.authoritative_summary_path(tmp_path).read_text(encoding="utf-8")
    )
    assert summary["mode"] == "auto_promoted"
    assert len(summary["promoted"]) == 1
    assert len(summary["unqualified"]) == 2


def test_promote_auto_promotes_multiple_qualifying_groups_independently(
    tmp_path: Path,
) -> None:
    """Two legitimately different schemas for the same cli-name each get
    their own independent promotion when both clear the gate -- no
    collapse to a single winner per case (SPEC §6 multi-variant)."""
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    _write_trial(
        tmp_path, "20260101-000002-aaa002", _TEMPLATE_B, "2024-01-01 10:00:00\n"
    )

    gate = PromotionGate(match_rate_threshold=0.4, min_sample_count=1)
    result = promote_auto(tmp_path, PromotionMetadata(user="tuyen"), default_gate=gate)

    dest_dir = paths.authoritative_dir(tmp_path, KEY)
    assert len(result.promoted) == 2
    # group1 is unsuffixed (the primary); group2 gets its own stable,
    # permanent v2 tag -- both sit side by side in the same flat directory.
    assert dest_dir / "template.textfsm" in result.promoted
    assert dest_dir / "template-v2.textfsm" in result.promoted

    # golden.hash / artifact.json are singular and unsuffixed -- never
    # golden-v2.hash / artifact-v2.json -- and end up reflecting whichever
    # group was promoted last (group2, since group1 always processes first).
    assert not (dest_dir / "golden-v2.hash").exists()
    assert not (dest_dir / "artifact-v2.json").exists()
    artifact = json.loads((dest_dir / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["group_id"] == "group2"


def test_promote_auto_appends_authoritative_log_across_repeated_runs(
    tmp_path: Path,
) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    metadata = PromotionMetadata(user="tuyen")

    promote_auto(tmp_path, metadata)
    promote_auto(tmp_path, metadata)

    log = json.loads(paths.authoritative_log_path(tmp_path).read_text(encoding="utf-8"))
    assert len(log) == 2


def test_promote_auto_archives_previous_content_when_representative_changes(
    tmp_path: Path,
) -> None:
    """Re-running promote_auto after new trials shift which variant is
    representative must archive the old template/recognizers content to
    history/ before overwriting it -- never silently discard it (§3.3)."""
    _write_trial(
        tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n", recognizers="r1"
    )

    first = promote_auto(tmp_path, PromotionMetadata(user="tuyen"))
    dest_dir = paths.authoritative_dir(tmp_path, KEY)
    assert first.promoted == [dest_dir / "template.textfsm"]
    original_template = (dest_dir / "template.textfsm").read_text(encoding="utf-8")
    assert original_template == _TEMPLATE

    history_dir = paths.authoritative_history_dir(tmp_path, KEY)
    assert not history_dir.exists()

    # Two more trials with a different (but same-schema) template make the
    # new variant more prevalent -- it becomes the representative.
    _write_trial(
        tmp_path,
        "20260101-000002-aaa002",
        _TEMPLATE_LINE_VARIANT,
        "goodbye world\n",
        recognizers="r2",
    )
    _write_trial(
        tmp_path,
        "20260101-000003-aaa003",
        _TEMPLATE_LINE_VARIANT,
        "third line\n",
        recognizers="r2",
    )

    second = promote_auto(tmp_path, PromotionMetadata(user="tuyen"))
    assert second.promoted == [dest_dir / "template.textfsm"]
    assert (dest_dir / "template.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_LINE_VARIANT
    assert (dest_dir / "recognizers.txt").read_text(encoding="utf-8") == "r2"

    archived_templates = list(history_dir.glob("template-*.textfsm"))
    assert len(archived_templates) == 1
    assert archived_templates[0].read_text(encoding="utf-8") == original_template

    archived_recognizers = list(history_dir.glob("recognizers-*.txt"))
    assert len(archived_recognizers) == 1
    assert archived_recognizers[0].read_text(encoding="utf-8") == "r1"


def test_promote_auto_does_not_archive_identical_content(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    metadata = PromotionMetadata(user="tuyen")

    promote_auto(tmp_path, metadata)
    promote_auto(tmp_path, metadata)

    history_dir = paths.authoritative_history_dir(tmp_path, KEY)
    assert not history_dir.exists()


def test_promote_user_reviewed_writes_suffixed_files_and_reports_unmatched(
    tmp_path: Path,
) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    _write_trial(tmp_path, "20260101-000002-aaa002", _TEMPLATE, "goodbye world\n")

    metadata = PromotionMetadata(user="tuyen", note="reviewed in standup")
    requests = [
        UserReviewedRequest(
            case_key="cisco/catalyst9200/ios-xe/show-clock", suffix="2"
        ),
        UserReviewedRequest(
            case_key="cisco/catalyst9200/ios-xe/does-not-exist", suffix="1"
        ),
    ]

    result = promote_user_reviewed(tmp_path, metadata, requests)

    assert len(result.promoted) == 1
    template_path = result.promoted[0]
    dest_dir = paths.authoritative_dir(tmp_path, KEY)
    # group1's major tag is "v1"; combined with the request's own minor
    # marker "2" -> "v1-2" -- distinct from group1's unsuffixed auto-
    # promoted files, which this leaves untouched.
    assert template_path == dest_dir / "template-v1-2.textfsm"
    assert (dest_dir / "recognizers-v1-2.txt").exists()

    data_dir = paths.promoted_data_dir(tmp_path, KEY)
    assert (data_dir / "sample-v1-2.txt").exists()
    assert (data_dir / "records-v1-2.json").exists()

    # artifact.json/golden.hash are singular and unsuffixed even though
    # the template/recognizers/data files themselves are suffixed.
    assert not (dest_dir / "artifact-v1-2.json").exists()
    artifact = json.loads((dest_dir / "artifact.json").read_text(encoding="utf-8"))
    assert artifact["mode"] == "user_reviewed"
    assert artifact["suffix"] == "v1-2"
    assert artifact["note"] == "reviewed in standup"

    assert result.unmatched_cases == ["cisco/catalyst9200/ios-xe/does-not-exist"]
    assert result.invalid_requests == []
    summary = json.loads(
        paths.authoritative_summary_path(tmp_path).read_text(encoding="utf-8")
    )
    assert summary["unmatched_cases"] == ["cisco/catalyst9200/ios-xe/does-not-exist"]


def test_promote_user_reviewed_skips_requests_with_no_usable_suffix(
    tmp_path: Path,
) -> None:
    """A missing or blank suffix would collide with (or silently pass as)
    an auto-promoted "current version" file, so it must never be written
    -- reported in invalid_requests instead."""
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    _write_trial(
        tmp_path, "20260101-000001-bbb001", _TEMPLATE, "hello world\n", key=OTHER_KEY
    )

    requests = [
        UserReviewedRequest(
            case_key="cisco/catalyst9200/ios-xe/show-clock", suffix=None
        ),
        UserReviewedRequest(
            case_key="cisco/catalyst9200/ios-xe/show-version", suffix="   "
        ),
    ]
    result = promote_user_reviewed(tmp_path, PromotionMetadata(user="tuyen"), requests)

    assert result.promoted == []
    assert set(result.invalid_requests) == {
        "cisco/catalyst9200/ios-xe/show-clock",
        "cisco/catalyst9200/ios-xe/show-version",
    }
    assert result.unmatched_cases == []
    assert not paths.authoritative_dir(tmp_path, KEY).exists()
    assert not paths.authoritative_dir(tmp_path, OTHER_KEY).exists()

    summary = json.loads(
        paths.authoritative_summary_path(tmp_path).read_text(encoding="utf-8")
    )
    assert set(summary["invalid_requests"]) == {
        "cisco/catalyst9200/ios-xe/show-clock",
        "cisco/catalyst9200/ios-xe/show-version",
    }


def test_promote_user_reviewed_only_considers_requested_cases(
    tmp_path: Path,
) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    _write_trial(
        tmp_path, "20260101-000001-bbb001", _TEMPLATE, "hello world\n", key=OTHER_KEY
    )

    requests = [
        UserReviewedRequest(case_key=OTHER_KEY.relative_path().as_posix(), suffix="1")
    ]
    result = promote_user_reviewed(tmp_path, PromotionMetadata(user="tuyen"), requests)

    assert len(result.promoted) == 1
    assert result.promoted[0] == (
        paths.authoritative_dir(tmp_path, OTHER_KEY) / "template-v1-1.textfsm"
    )
    # KEY's case would have cleared the default gate too, but was never
    # requested, so it must stay untouched.
    assert not paths.authoritative_dir(tmp_path, KEY).exists()


def test_promote_user_reviewed_uses_per_request_gate_override(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE, "hello world\n")
    _write_trial(
        tmp_path, "20260101-000002-aaa002", _TEMPLATE_B, "2024-01-01 10:00:00\n"
    )

    loose_gate = PromotionGate(match_rate_threshold=0.4, min_sample_count=1)
    requests = [
        UserReviewedRequest(
            case_key="cisco/catalyst9200/ios-xe/show-clock",
            suffix="1",
            gate=loose_gate,
        )
    ]

    result = promote_user_reviewed(tmp_path, PromotionMetadata(user="tuyen"), requests)

    # Both group1 and group2 have ratio_of_passed 0.5 -- fails the default
    # 1.0 gate but clears the request's own 0.4 override. Each gets its own
    # major tag combined with the same minor marker: v1-1 and v2-1.
    dest_dir = paths.authoritative_dir(tmp_path, KEY)
    assert len(result.promoted) == 2
    assert dest_dir / "template-v1-1.textfsm" in result.promoted
    assert dest_dir / "template-v2-1.textfsm" in result.promoted
