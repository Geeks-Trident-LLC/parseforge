"""YAML config-file loading for the `trial` and `generate-template` CLI commands.

CLI input parsing, not domain logic — kept next to the CLI rather than in
pipeline.py/generation.py, mirroring how cli/main.py already assembles
LLMProviderConfig/TrialMetadata itself instead of pushing that into
pipeline.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml


@dataclass(frozen=True)
class TrialConfig:
    vendor: str
    family: str
    os: str
    version: str
    connector: str
    host: str
    username: str
    password: str
    device_type: str
    naming_provider: str
    generation_provider: str
    generation_api_key: str
    generation_model: str
    commands: list[str]
    user: str
    naming_api_key: str | None = None
    naming_model: str | None = None
    email: str | None = None
    description: str | None = None
    note: str | None = None
    workers: int = 1
    path: str | None = None


@dataclass(frozen=True)
class GenerationRequestConfig:
    provider: str
    model: str
    api_key: str | None = None
    connector: str | None = None
    host: str | None = None
    username: str | None = None
    password: str | None = None
    device_type: str | None = None
    env: str | None = None
    cmdline: str | None = None
    sample_file: str | None = None


_TRIAL_REQUIRED = (
    "vendor",
    "family",
    "os",
    "version",
    "connector",
    "host",
    "username",
    "password",
    "device_type",
    "naming_provider",
    "generation_provider",
    "generation_api_key",
    "generation_model",
    "commands",
    "user",
)

_GENERATION_REQUIRED = ("provider", "model")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise click.ClickException(f"config file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise click.ClickException(f"{path}: config file must be a YAML mapping")
    return raw


def _require_keys(raw: dict[str, Any], required: tuple[str, ...], path: Path) -> None:
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise click.ClickException(
            f"{path}: missing required config key(s): {', '.join(missing)}"
        )


def load_trial_config(path: Path) -> TrialConfig:
    raw = _load_yaml_mapping(path)
    _require_keys(raw, _TRIAL_REQUIRED, path)

    commands = raw["commands"]
    if not isinstance(commands, list) or not all(isinstance(c, str) for c in commands):
        raise click.ClickException(f"{path}: 'commands' must be a list of strings")

    return TrialConfig(
        vendor=raw["vendor"],
        family=raw["family"],
        os=raw["os"],
        version=raw["version"],
        connector=raw["connector"],
        host=raw["host"],
        username=raw["username"],
        password=raw["password"],
        device_type=raw["device_type"],
        naming_provider=raw["naming_provider"],
        naming_api_key=raw.get("naming_api_key"),
        naming_model=raw.get("naming_model"),
        generation_provider=raw["generation_provider"],
        generation_api_key=raw["generation_api_key"],
        generation_model=raw["generation_model"],
        commands=commands,
        user=raw["user"],
        email=raw.get("email"),
        description=raw.get("description"),
        note=raw.get("notes"),
        workers=int(raw.get("workers", 1)),
        path=raw.get("path"),
    )


def load_generation_config(path: Path) -> GenerationRequestConfig:
    raw = _load_yaml_mapping(path)
    _require_keys(raw, _GENERATION_REQUIRED, path)

    return GenerationRequestConfig(
        provider=raw["provider"],
        model=raw["model"],
        api_key=raw.get("api_key"),
        connector=raw.get("connector"),
        host=raw.get("host"),
        username=raw.get("username"),
        password=raw.get("password"),
        device_type=raw.get("device_type"),
        env=raw.get("env"),
        cmdline=raw.get("cmdline"),
        sample_file=raw.get("sample_file"),
    )
