from __future__ import annotations

import json
from pathlib import Path

import pytest

from parseforge import paths
from parseforge.integration import (
    _load_reference,
    build_integration,
    build_reference_summary,
    write_reference_summary,
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

_TEMPLATE_A = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"
_TEMPLATE_A2 = "Value LINE (\\S.*)\n\nStart\n  ^${LINE} -> Record\n"
_TEMPLATE_B = (
    "Value DATE (\\S+)\nValue TIME (\\S+)\n\nStart\n  ^${DATE}\\s+${TIME} -> Record\n"
)
_TEMPLATE_BROKEN = "this is not a valid textfsm template !!!"


def _write_trial(
    store_root: Path,
    run_id: str,
    template: str,
    sample: str,
    key: paths.DeviceKey = KEY,
    passed: bool = True,
) -> Path:
    run_dir = paths.trial_run_dir(store_root, key, run_id=run_id)
    (run_dir / "derive").mkdir(parents=True, exist_ok=True)
    (run_dir / "samples").mkdir(parents=True, exist_ok=True)
    (run_dir / "derive" / "template.textfsm").write_text(template, encoding="utf-8")
    (run_dir / "samples" / "sample.txt").write_text(sample, encoding="utf-8")
    (run_dir / "summary.json").write_text(
        json.dumps({"passed": passed}), encoding="utf-8"
    )
    return run_dir


def test_build_integration_clusters_by_schema_and_variant(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    _write_trial(tmp_path, "20260101-000002-aaa002", _TEMPLATE_A, "goodbye world\n")
    _write_trial(tmp_path, "20260101-000003-aaa003", _TEMPLATE_A2, "third line\n")
    _write_trial(
        tmp_path, "20260101-000004-aaa004", _TEMPLATE_B, "2024-01-01 10:00:00\n"
    )
    # A broken template genuinely wouldn't self-validate in the real
    # pipeline, so its own trial would be recorded as failed.
    _write_trial(
        tmp_path, "20260101-000005-aaa005", _TEMPLATE_BROKEN, "anything\n", passed=False
    )

    reference = build_integration(tmp_path, KEY)

    assert set(reference) == {"group1", "group2"}

    group1 = reference["group1"]
    assert group1.keys == ["LINE"]
    assert set(group1.variants) == {"1", "2"}
    assert group1.variants["1"].exact_template_count == 2
    assert group1.variants["1"].exact_records_count == 2
    assert group1.variants["2"].exact_template_count == 1
    assert group1.variants["2"].exact_records_count == 1

    group2 = reference["group2"]
    assert group2.keys == ["DATE", "TIME"]
    assert set(group2.variants) == {"1"}
    assert group2.variants["1"].exact_template_count == 1

    integration_dir = paths.integration_dir(tmp_path, KEY)
    assert (integration_dir / "group1-template1.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_A
    assert (integration_dir / "group1-template2.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_A2
    assert (integration_dir / "group2-template1.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_B
    # The broken trial's template never produced a group, so no group3 file.
    assert not (integration_dir / "group3-template1.textfsm").exists()

    reference_json = integration_dir / "reference.json"
    assert reference_json.exists()
    on_disk = json.loads(reference_json.read_text(encoding="utf-8"))
    # 5 trial dirs total (including the one whose broken template never
    # clustered into any group) -- total_case_count counts all of them.
    assert on_disk["total_case_count"] == 5
    assert set(on_disk["groups"]) == {"group1", "group2"}
    assert on_disk["groups"]["group1"]["group_case_count"] == 3
    assert on_disk["groups"]["group2"]["group_case_count"] == 1
    reloaded = _load_reference(reference_json)
    assert reloaded == reference


def test_build_integration_excludes_failed_trial_even_if_template_self_parses(
    tmp_path: Path,
) -> None:
    """A trial whose own summary.json says passed: false must never be
    clustered, even when its template happens to parse its own sample --
    e.g. a truncated (not-ready) generation whose partial output still
    self-validates. This can't be caught by re-parsing template.textfsm
    against sample.txt alone, only by trusting the trial's own verdict."""
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    _write_trial(
        tmp_path,
        "20260101-000002-aaa002",
        _TEMPLATE_A,
        "goodbye world\n",
        passed=False,
    )

    reference = build_integration(tmp_path, KEY)

    assert set(reference) == {"group1"}
    assert reference["group1"].variants["1"].exact_template_count == 1

    integration_dir = paths.integration_dir(tmp_path, KEY)
    on_disk = json.loads(
        (integration_dir / "reference.json").read_text(encoding="utf-8")
    )
    # Both trials count toward total_case_count (the failed one lowers the
    # achievable match rate); only the passed one clusters into a group.
    assert on_disk["total_case_count"] == 2
    assert on_disk["groups"]["group1"]["group_case_count"] == 1


def test_build_integration_excludes_trial_with_no_summary_json(
    tmp_path: Path,
) -> None:
    """A trial dir missing summary.json entirely (e.g. the pipeline never
    got far enough to write it) is treated the same as a failed trial --
    not eligible for clustering."""
    run_dir = paths.trial_run_dir(tmp_path, KEY, run_id="20260101-000001-aaa001")
    (run_dir / "derive").mkdir(parents=True)
    (run_dir / "samples").mkdir(parents=True)
    (run_dir / "derive" / "template.textfsm").write_text(_TEMPLATE_A, encoding="utf-8")
    (run_dir / "samples" / "sample.txt").write_text("hello world\n", encoding="utf-8")

    reference = build_integration(tmp_path, KEY)

    assert reference == {}


def test_build_integration_with_no_trials_writes_empty_reference(
    tmp_path: Path,
) -> None:
    reference = build_integration(tmp_path, KEY)

    assert reference == {}
    integration_dir = paths.integration_dir(tmp_path, KEY)
    on_disk = json.loads(
        (integration_dir / "reference.json").read_text(encoding="utf-8")
    )
    assert on_disk == {"total_case_count": 0, "groups": {}}


def test_build_integration_is_idempotent_full_rebuild(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")

    first = build_integration(tmp_path, KEY)
    second = build_integration(tmp_path, KEY)

    assert first == second
    assert first["group1"].variants["1"].exact_template_count == 1


def test_build_reference_summary_computes_ratios(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    _write_trial(tmp_path, "20260101-000002-aaa002", _TEMPLATE_A, "goodbye world\n")
    _write_trial(tmp_path, "20260101-000003-aaa003", _TEMPLATE_A2, "third line\n")
    build_integration(tmp_path, KEY)

    summary = build_reference_summary(tmp_path)

    assert summary["trial_project"] == str(paths.tier_root(tmp_path, paths.TRIALS))
    case = summary["cases"]["cisco/catalyst9200/ios-xe/show-clock"]
    assert case["total_case_count"] == 3

    group1 = case["groups"]["group1"]
    assert group1["keys"] == ["LINE"]
    assert group1["case_count"] == 3
    assert group1["ratio"] == pytest.approx(1.0)
    assert group1["variants"]["1"]["ratio_of_group"] == pytest.approx(2 / 3)
    assert group1["variants"]["1"]["ratio_of_total"] == pytest.approx(2 / 3)
    assert group1["variants"]["2"]["ratio_of_group"] == pytest.approx(1 / 3)
    assert group1["variants"]["2"]["ratio_of_total"] == pytest.approx(1 / 3)


def test_build_reference_summary_covers_multiple_cases(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    build_integration(tmp_path, KEY)

    _write_trial(
        tmp_path,
        "20260101-000001-bbb001",
        _TEMPLATE_B,
        "2024-01-01 10:00:00\n",
        key=OTHER_KEY,
    )
    build_integration(tmp_path, OTHER_KEY)

    summary = build_reference_summary(tmp_path)

    assert set(summary["cases"]) == {
        "cisco/catalyst9200/ios-xe/show-clock",
        "cisco/catalyst9200/ios-xe/show-version",
    }


def test_build_reference_summary_with_no_integration_dir_is_empty(
    tmp_path: Path,
) -> None:
    summary = build_reference_summary(tmp_path)

    assert summary == {
        "trial_project": str(paths.tier_root(tmp_path, paths.TRIALS)),
        "cases": {},
    }


def test_write_reference_summary_writes_file(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    build_integration(tmp_path, KEY)

    path = write_reference_summary(tmp_path)

    assert path == paths.reference_summary_path(tmp_path)
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "cisco/catalyst9200/ios-xe/show-clock" in on_disk["cases"]


def test_write_reference_summary_lands_at_integration_project_root(
    tmp_path: Path,
) -> None:
    """reference-summary.json sits directly under integration/ (the
    "integration-project" root) -- a sibling of every cli-name's own
    integration directory, not nested inside one of them."""
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    build_integration(tmp_path, KEY)

    path = write_reference_summary(tmp_path)

    # Hardcoded, independent of paths.reference_summary_path() itself,
    # so this fails if that helper's own path resolution ever regresses.
    assert path == tmp_path / "integration" / "reference-summary.json"
    assert paths.integration_dir(tmp_path, KEY).is_relative_to(path.parent)
    assert path.exists()
