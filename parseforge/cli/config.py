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

# Providers that don't take an API key at all — Vertex AI relies on GCP's
# Application Default Credentials, Bedrock on AWS's own credential chain,
# and OCI on locally-configured request-signing credentials (see
# naming/providers/vertexai.py, naming/providers/bedrock.py, and
# naming/providers/oci.py). api_key is required for every other
# provider, but never for these; kept as a small named set (rather than
# scattered `provider not in (...)` checks) so a future provider with
# the same trait is a one-line addition.
NO_API_KEY_PROVIDERS = frozenset({"vertexai", "bedrock", "oci"})


@dataclass(frozen=True)
class TrialConfig:
    """``provider``/``api_key``/``model`` are one shared LLM source for both
    naming (cli-name resolution) and generation — the common case where a
    trial doesn't need two different providers. Use the ``run`` command's
    separate ``--naming-*``/``--generation-*`` flags if you actually do."""

    vendor: str
    family: str
    os: str
    version: str
    connector: str
    host: str
    username: str
    password: str
    device_type: str
    provider: str
    model: str
    commands: list[str]
    user: str
    # Required unless provider is in NO_API_KEY_PROVIDERS — see
    # load_trial_config()'s explicit check; not in the dataclass's
    # required-field position since it's conditionally optional.
    api_key: str | None = None
    email: str | None = None
    description: str | None = None
    note: str | None = None
    workers: int = 1
    path: str | None = None
    # Only meaningful for provider: azure — no fixed base_url or model
    # catalog there (see naming/providers/azure.py). endpoint/api_version
    # are ignored by every other provider; deployment replaces the usual
    # "model" concept and is what actually gets sent as the generation
    # model argument (see cli/main.py's trial_cmd).
    endpoint: str | None = None
    api_version: str | None = None
    deployment: str | None = None
    # Only meaningful for provider: vertexai — see
    # naming/providers/vertexai.py. Falls back to VERTEXAI_PROJECT/
    # VERTEXAI_REGION if omitted, same as api_key falls back to a
    # provider's own env var.
    project: str | None = None
    location: str | None = None
    # Only meaningful for provider: bedrock — see
    # naming/providers/bedrock.py. Falls back to BEDROCK_REGION, then
    # BEDROCK_DEFAULT_REGION, if omitted.
    region: str | None = None
    # Only meaningful for provider: oci — see naming/providers/oci.py.
    # compartment_id falls back to OCI_COMPARTMENT_ID if omitted; region
    # (shared with the bedrock field above) falls back to OCI_REGION,
    # then whatever region is already set in ~/.oci/config.
    compartment_id: str | None = None


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
    # Only meaningful for provider: azure — see TrialConfig above.
    endpoint: str | None = None
    api_version: str | None = None
    deployment: str | None = None
    # Only meaningful for provider: vertexai — see TrialConfig above.
    project: str | None = None
    location: str | None = None
    # Only meaningful for provider: bedrock — see TrialConfig above.
    region: str | None = None
    # Only meaningful for provider: oci — see TrialConfig above.
    compartment_id: str | None = None


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
    "provider",
    "model",
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

    provider = raw["provider"]
    if provider not in NO_API_KEY_PROVIDERS and not raw.get("api_key"):
        raise click.ClickException(f"{path}: missing required config key(s): api_key")

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
        provider=provider,
        api_key=raw.get("api_key"),
        model=raw["model"],
        commands=commands,
        user=raw["user"],
        email=raw.get("email"),
        description=raw.get("description"),
        note=raw.get("notes"),
        workers=int(raw.get("workers", 1)),
        path=raw.get("path"),
        endpoint=raw.get("endpoint"),
        api_version=raw.get("api_version"),
        deployment=raw.get("deployment"),
        project=raw.get("project"),
        location=raw.get("location"),
        region=raw.get("region"),
        compartment_id=raw.get("compartment_id"),
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
        endpoint=raw.get("endpoint"),
        api_version=raw.get("api_version"),
        deployment=raw.get("deployment"),
        project=raw.get("project"),
        location=raw.get("location"),
        region=raw.get("region"),
        compartment_id=raw.get("compartment_id"),
    )
