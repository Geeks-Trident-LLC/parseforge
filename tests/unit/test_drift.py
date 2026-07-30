from __future__ import annotations

import json
from pathlib import Path

import pytest

from parseforge import paths
from parseforge.drift import DriftGate, check_drift

KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    cli_name="show-clock",
)

_TEMPLATE = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"
_GOOD_SAMPLE = "hello world\n"
_BAD_SAMPLE = ""


def _promote(
    store_root: Path,
    key: paths.DeviceKey = KEY,
    template: str = _TEMPLATE,
    suffix: str | None = None,
) -> Path:
    dest_dir = paths.authoritative_dir(store_root, key)
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix_part = f"-{suffix}" if suffix else ""
    dest = dest_dir / f"template{suffix_part}.textfsm"
    dest.write_text(template, encoding="utf-8")
    return dest


def test_check_drift_raises_when_variant_never_promoted(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        check_drift(tmp_path, KEY, _GOOD_SAMPLE)


def test_check_drift_passes_and_reports_ok(tmp_path: Path) -> None:
    _promote(tmp_path)

    result = check_drift(tmp_path, KEY, _GOOD_SAMPLE)

    assert result.passed is True
    assert result.match_rate == 1.0
    assert result.status == "ok"
    assert result.requeued_to is None


def test_check_drift_fails_and_reports_drifting(tmp_path: Path) -> None:
    _promote(tmp_path)

    result = check_drift(tmp_path, KEY, _BAD_SAMPLE)

    assert result.passed is False
    assert result.match_rate == 0.0
    assert result.status == "drifting"
    assert result.requeued_to is not None


def test_check_drift_requeues_failing_sample_into_trials(tmp_path: Path) -> None:
    _promote(tmp_path)

    result = check_drift(tmp_path, KEY, _BAD_SAMPLE)

    requeued_dir = Path(result.requeued_to)
    assert requeued_dir.exists()
    assert (requeued_dir / "samples" / "sample.txt").read_text(
        encoding="utf-8"
    ) == _BAD_SAMPLE
    # No summary.json yet — integration.build_integration must not treat
    # a requeued-but-not-yet-regenerated run as passed evidence.
    assert not (requeued_dir / "summary.json").exists()


def test_check_drift_writes_drift_log_shape(tmp_path: Path) -> None:
    _promote(tmp_path)
    check_drift(tmp_path, KEY, _GOOD_SAMPLE)

    log_path = paths.drift_log_path(tmp_path, KEY)
    log = json.loads(log_path.read_text(encoding="utf-8"))

    assert len(log) == 1
    entry = log[0]
    assert entry["case"] == "cisco/catalyst9200/ios-xe/show-clock"
    assert entry["suffix"] is None
    assert entry["passed"] is True
    assert entry["match_rate"] == 1.0
    assert entry["status"] == "ok"
    assert "checked_at" in entry
    assert entry["requeued_to"] is None


def test_check_drift_appends_across_runs(tmp_path: Path) -> None:
    _promote(tmp_path)
    check_drift(tmp_path, KEY, _GOOD_SAMPLE)
    check_drift(tmp_path, KEY, _GOOD_SAMPLE)

    log = json.loads(paths.drift_log_path(tmp_path, KEY).read_text(encoding="utf-8"))
    assert len(log) == 2


def test_check_drift_rolling_match_rate(tmp_path: Path) -> None:
    _promote(tmp_path)
    gate = DriftGate(match_rate_threshold=1.0, window=4)

    check_drift(tmp_path, KEY, _GOOD_SAMPLE, gate=gate)
    check_drift(tmp_path, KEY, _GOOD_SAMPLE, gate=gate)
    check_drift(tmp_path, KEY, _GOOD_SAMPLE, gate=gate)
    result = check_drift(tmp_path, KEY, _BAD_SAMPLE, gate=gate)

    assert result.match_rate == 0.75
    assert result.status == "drifting"


def test_check_drift_rolling_window_trims_old_entries(tmp_path: Path) -> None:
    _promote(tmp_path)
    gate = DriftGate(match_rate_threshold=1.0, window=2)

    # Oldest failure should fall out of a window of 2 once two more
    # passing checks have happened.
    check_drift(tmp_path, KEY, _BAD_SAMPLE, gate=gate)
    check_drift(tmp_path, KEY, _GOOD_SAMPLE, gate=gate)
    result = check_drift(tmp_path, KEY, _GOOD_SAMPLE, gate=gate)

    assert result.match_rate == 1.0
    assert result.status == "ok"


def test_check_drift_recovers_to_ok_after_drifting(tmp_path: Path) -> None:
    _promote(tmp_path)
    gate = DriftGate(match_rate_threshold=0.5, window=2)

    check_drift(tmp_path, KEY, _BAD_SAMPLE, gate=gate)
    result = check_drift(tmp_path, KEY, _GOOD_SAMPLE, gate=gate)

    assert result.match_rate == 0.5
    assert result.status == "ok"


def test_check_drift_tracks_variants_independently(tmp_path: Path) -> None:
    _promote(tmp_path, suffix=None)
    _promote(tmp_path, suffix="v2")

    check_drift(tmp_path, KEY, _BAD_SAMPLE, suffix=None)
    result = check_drift(tmp_path, KEY, _GOOD_SAMPLE, suffix="v2")

    assert result.match_rate == 1.0
    assert result.status == "ok"

    log = json.loads(paths.drift_log_path(tmp_path, KEY).read_text(encoding="utf-8"))
    assert [entry["suffix"] for entry in log] == [None, "v2"]
