from __future__ import annotations

from pathlib import Path

from parseforge import paths

KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    cli_name="show-clock",
)


def test_device_key_relative_path() -> None:
    assert KEY.relative_path() == Path("cisco", "catalyst9200", "ios-xe", "show-clock")


def test_tier_path_resolves_under_store_root(tmp_path: Path) -> None:
    assert paths.tier_path(tmp_path, paths.TRIALS, KEY) == (
        tmp_path / "trials" / KEY.relative_path()
    )


def test_trial_run_dir_uses_explicit_run_id(tmp_path: Path) -> None:
    run_dir = paths.trial_run_dir(tmp_path, KEY, run_id="20260101-000001-aaa001")

    assert run_dir == (
        tmp_path / "trials" / KEY.relative_path() / "20260101-000001-aaa001"
    )


def test_integration_dir_resolves_under_integration_tier(tmp_path: Path) -> None:
    assert paths.integration_dir(tmp_path, KEY) == (
        tmp_path / "integration" / KEY.relative_path()
    )


def test_promoted_data_dir_nests_under_authoritative_dir(tmp_path: Path) -> None:
    assert paths.promoted_data_dir(tmp_path, KEY) == (
        paths.authoritative_dir(tmp_path, KEY) / "data"
    )


def test_authoritative_summary_path_sits_at_authoritative_tier_root(
    tmp_path: Path,
) -> None:
    assert paths.authoritative_summary_path(tmp_path) == (
        tmp_path / "authoritative" / "authoritative-summary.json"
    )


def test_authoritative_log_path_sits_at_authoritative_tier_root(
    tmp_path: Path,
) -> None:
    assert paths.authoritative_log_path(tmp_path) == (
        tmp_path / "authoritative" / "authoritative-log.json"
    )


def test_drift_log_path_nests_under_authoritative_dir(tmp_path: Path) -> None:
    assert paths.drift_log_path(tmp_path, KEY) == (
        paths.authoritative_dir(tmp_path, KEY) / "drift-log.json"
    )


def test_authoritative_history_dir_nests_under_authoritative_dir(
    tmp_path: Path,
) -> None:
    assert paths.authoritative_history_dir(tmp_path, KEY) == (
        paths.authoritative_dir(tmp_path, KEY) / "history"
    )


def test_discover_device_keys_with_no_trials_dir_is_empty(tmp_path: Path) -> None:
    assert paths.discover_device_keys(tmp_path) == []


def test_discover_device_keys_finds_every_cli_name(tmp_path: Path) -> None:
    other_key = paths.DeviceKey(
        vendor="cisco", family="catalyst9200", os="ios-xe", cli_name="show-version"
    )
    paths.trial_run_dir(tmp_path, KEY, run_id="20260101-000001-aaa001").mkdir(
        parents=True
    )
    paths.trial_run_dir(tmp_path, other_key, run_id="20260101-000001-bbb001").mkdir(
        parents=True
    )

    assert paths.discover_device_keys(tmp_path) == [KEY, other_key]
