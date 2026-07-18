"""Live end-to-end trial pipeline test: real Cisco sandbox + Anthropic
for both naming and generation.

Skipped by default — run with `pytest --real`, ANTHROPIC_API_KEY, and
CISCO_SANDBOX_HOST/CISCO_SANDBOX_USERNAME/CISCO_SANDBOX_PASSWORD set
(CISCO_SANDBOX_DEVICE_TYPE optional, defaults to "cisco_ios"). Opens a
real SSH connection and makes real Anthropic API calls (costs tokens).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip(
    "netmiko", reason="netmiko is an optional extra (parseforge[sampling])"
)

from parseforge.naming import AnthropicRegexBuilder, CliContext  # noqa: E402
from parseforge.pipeline import (  # noqa: E402
    LLMProviderConfig,
    TrialMetadata,
    run_command_pipeline,
)
from parseforge.sampling import DeviceConnection  # noqa: E402
from parseforge.sampling.backends import NetmikoSampler  # noqa: E402

pytestmark = pytest.mark.real

MODEL = "claude-haiku-4-5-20251001"

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def test_full_trial_pipeline_show_clock(
    anthropic_key: str, cisco_sandbox_connection: DeviceConnection, tmp_path: Path
) -> None:
    naming_builder = AnthropicRegexBuilder(api_key=anthropic_key, model=MODEL)
    generation_config = LLMProviderConfig(
        provider="anthropic", api_key=anthropic_key, model=MODEL
    )

    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        cisco_sandbox_connection,
        naming_builder,
        NetmikoSampler(),
        generation_config,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
        metadata=TrialMetadata(
            project="parseforge-integration-test",
            description="live full-pipeline test via Anthropic",
        ),
    )

    assert result.cli_name == "show-clock"
    assert result.passed is True
    assert result.duration_ms > 0

    samples_dir = result.run_dir / "samples"
    derive_dir = result.run_dir / "derive"

    sample = (samples_dir / "sample.txt").read_text(encoding="utf-8")
    assert sample.strip()
    assert (samples_dir / "sample-for-prompt.txt").exists()

    template = (derive_dir / "template.textfsm").read_text(encoding="utf-8")
    assert template.strip()
    assert (derive_dir / "llm-template.textfsm").exists()
    assert (derive_dir / "readable-dsl.txt").exists()
    assert (derive_dir / "recognizers.txt").exists()

    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["passed"] is True
    assert summary["metadata"]["project"] == "parseforge-integration-test"
    assert summary["usage"]["generation_usage"]["total_tokens"] > 0
    assert summary["provider_info"]["generation"] == {
        "provider": "anthropic",
        "model": MODEL,
    }
    # naming_usage is None on a cache hit; this is a fresh tmp_path index,
    # so this run must be a genuine cache miss (real LLM call happened).
    assert summary["usage"]["naming_usage"] is not None
    assert summary["usage"]["naming_usage"]["total_tokens"] > 0
