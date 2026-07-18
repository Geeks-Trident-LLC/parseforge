from __future__ import annotations

from pathlib import Path

from parseforge import paths

KEY = paths.DeviceKey(
    vendor="cisco",
    family="catalyst9200",
    os="ios-xe",
    version="17.9.1",
    cli_name="show-clock",
)


def test_device_key_relative_path() -> None:
    assert KEY.relative_path() == Path(
        "cisco", "catalyst9200", "ios-xe", "17.9.1", "show-clock"
    )


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


def test_authoritative_group_dir_nests_under_authoritative_dir(
    tmp_path: Path,
) -> None:
    assert paths.authoritative_group_dir(tmp_path, KEY, "group1") == (
        paths.authoritative_dir(tmp_path, KEY) / "group1"
    )
