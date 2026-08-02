from __future__ import annotations

from pathlib import Path

import click
import pytest
import yaml

from parseforge.cli.config import load_generation_config, load_trial_config

_VALID_TRIAL: dict = {
    "vendor": "cisco",
    "family": "catalyst9200",
    "os": "ios-xe",
    "version": "17.9.1",
    "connector": "netmiko",
    "host": "10.0.0.1",
    "username": "admin",
    "password": "secret",
    "device_type": "cisco_ios",
    "provider": "anthropic",
    "api_key": "sk-test",
    "model": "claude-haiku-4-5-20251001",
    "commands": ["show clock"],
    "user": "alice",
}


def _write(path: Path, data: dict) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_load_trial_config_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(click.ClickException, match="not found"):
        load_trial_config(tmp_path / "missing.yaml")


def test_load_trial_config_not_a_mapping_raises(tmp_path: Path) -> None:
    path = tmp_path / "trial.yaml"
    path.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(click.ClickException, match="YAML mapping"):
        load_trial_config(path)


def test_load_trial_config_missing_required_keys(tmp_path: Path) -> None:
    path = _write(tmp_path / "trial.yaml", {"vendor": "cisco"})
    with pytest.raises(click.ClickException, match="missing required config key"):
        load_trial_config(path)


def test_load_trial_config_commands_must_be_list_of_strings(tmp_path: Path) -> None:
    data = dict(_VALID_TRIAL, commands="show clock")
    path = _write(tmp_path / "trial.yaml", data)
    with pytest.raises(click.ClickException, match="'commands' must be a list"):
        load_trial_config(path)


def test_load_trial_config_full(tmp_path: Path) -> None:
    data = dict(
        _VALID_TRIAL,
        email="alice@example.com",
        description="desc",
        notes="fyi",
        workers=4,
        path="/tmp/store",
        endpoint="https://my-resource.openai.azure.com",
        api_version="2024-06-01",
        deployment="my-deployment",
    )
    path = _write(tmp_path / "trial.yaml", data)

    cfg = load_trial_config(path)

    assert cfg.vendor == "cisco"
    assert cfg.provider == "anthropic"
    assert cfg.api_key == "sk-test"
    assert cfg.model == "claude-haiku-4-5-20251001"
    assert cfg.commands == ["show clock"]
    assert cfg.user == "alice"
    assert cfg.note == "fyi"
    assert cfg.workers == 4
    assert cfg.path == "/tmp/store"
    assert cfg.endpoint == "https://my-resource.openai.azure.com"
    assert cfg.api_version == "2024-06-01"
    assert cfg.deployment == "my-deployment"


def test_load_trial_config_defaults(tmp_path: Path) -> None:
    path = _write(tmp_path / "trial.yaml", _VALID_TRIAL)

    cfg = load_trial_config(path)

    assert cfg.email is None
    assert cfg.note is None
    assert cfg.workers == 1
    assert cfg.path is None
    assert cfg.endpoint is None
    assert cfg.api_version is None
    assert cfg.deployment is None


def test_load_generation_config_missing_required_keys(tmp_path: Path) -> None:
    path = _write(tmp_path / "gen.yaml", {"provider": "anthropic"})
    with pytest.raises(click.ClickException, match="missing required config key"):
        load_generation_config(path)


def test_load_generation_config_full(tmp_path: Path) -> None:
    data = {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
        "api_key": "sk-test",
        "sample_file": "sample.txt",
    }
    path = _write(tmp_path / "gen.yaml", data)

    cfg = load_generation_config(path)

    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-haiku-4-5-20251001"
    assert cfg.sample_file == "sample.txt"
    assert cfg.connector is None
    assert cfg.endpoint is None
    assert cfg.api_version is None
    assert cfg.deployment is None


def test_load_generation_config_azure_fields(tmp_path: Path) -> None:
    data = {
        "provider": "azure",
        "model": "unused-for-azure",
        "api_key": "sk-test",
        "sample_file": "sample.txt",
        "endpoint": "https://my-resource.openai.azure.com",
        "api_version": "2024-06-01",
        "deployment": "my-deployment",
    }
    path = _write(tmp_path / "gen.yaml", data)

    cfg = load_generation_config(path)

    assert cfg.endpoint == "https://my-resource.openai.azure.com"
    assert cfg.api_version == "2024-06-01"
    assert cfg.deployment == "my-deployment"
