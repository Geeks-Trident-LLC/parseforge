from __future__ import annotations

import json
from pathlib import Path

from parseforge import paths
from parseforge.integration import _load_reference, build_integration

KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    cli_name="show-clock",
)

_TEMPLATE_A = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"
_TEMPLATE_A2 = "Value LINE (\\S.*)\n\nStart\n  ^${LINE} -> Record\n"
_TEMPLATE_B = (
    "Value DATE (\\S+)\nValue TIME (\\S+)\n\nStart\n  ^${DATE}\\s+${TIME} -> Record\n"
)
_TEMPLATE_BROKEN = "this is not a valid textfsm template !!!"


def _write_trial(store_root: Path, run_id: str, template: str, sample: str) -> Path:
    run_dir = paths.trial_run_dir(store_root, KEY, run_id=run_id)
    (run_dir / "derive").mkdir(parents=True, exist_ok=True)
    (run_dir / "samples").mkdir(parents=True, exist_ok=True)
    (run_dir / "derive" / "template.textfsm").write_text(template, encoding="utf-8")
    (run_dir / "samples" / "sample.txt").write_text(sample, encoding="utf-8")
    return run_dir


def test_build_integration_clusters_by_schema_and_variant(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")
    _write_trial(tmp_path, "20260101-000002-aaa002", _TEMPLATE_A, "goodbye world\n")
    _write_trial(tmp_path, "20260101-000003-aaa003", _TEMPLATE_A2, "third line\n")
    _write_trial(
        tmp_path, "20260101-000004-aaa004", _TEMPLATE_B, "2024-01-01 10:00:00\n"
    )
    _write_trial(tmp_path, "20260101-000005-aaa005", _TEMPLATE_BROKEN, "anything\n")

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
    assert (integration_dir / "template1-group1.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_A
    assert (integration_dir / "template2-group1.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_A2
    assert (integration_dir / "template1-group2.textfsm").read_text(
        encoding="utf-8"
    ) == _TEMPLATE_B
    # The broken trial's template never produced a group, so no group3 file.
    assert not (integration_dir / "template1-group3.textfsm").exists()

    reference_json = integration_dir / "reference.json"
    assert reference_json.exists()
    on_disk = json.loads(reference_json.read_text(encoding="utf-8"))
    assert set(on_disk) == {"group1", "group2"}

    reloaded = _load_reference(reference_json)
    assert reloaded == reference


def test_build_integration_with_no_trials_writes_empty_reference(
    tmp_path: Path,
) -> None:
    reference = build_integration(tmp_path, KEY)

    assert reference == {}
    integration_dir = paths.integration_dir(tmp_path, KEY)
    assert (
        json.loads((integration_dir / "reference.json").read_text(encoding="utf-8"))
        == {}
    )


def test_build_integration_is_idempotent_full_rebuild(tmp_path: Path) -> None:
    _write_trial(tmp_path, "20260101-000001-aaa001", _TEMPLATE_A, "hello world\n")

    first = build_integration(tmp_path, KEY)
    second = build_integration(tmp_path, KEY)

    assert first == second
    assert first["group1"].variants["1"].exact_template_count == 1
