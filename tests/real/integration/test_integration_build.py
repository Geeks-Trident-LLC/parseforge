"""Live integration-build test: two real trial runs (real Cisco sandbox +
real DeepSeek naming/generation calls) clustered by build_integration().

Skipped by default — run with `pytest --real`, DEEPSEEK_API_KEY, and
CISCO_SANDBOX_HOST/CISCO_SANDBOX_USERNAME/CISCO_SANDBOX_PASSWORD set
(CISCO_SANDBOX_DEVICE_TYPE optional, defaults to "cisco_ios"). Opens two
real SSH connections and makes real DeepSeek API calls (costs tokens) —
naming resolves from cache after the first run, but generation always
calls the LLM fresh per trial, which is exactly what build_integration's
clustering needs real (non-fixture) variance to exercise.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip(
    "netmiko", reason="netmiko is an optional extra (parseforge[sampling])"
)

from parseforge import paths  # noqa: E402
from parseforge.integration import (  # noqa: E402
    build_integration,
    write_reference_summary,
)
from parseforge.naming import CliContext, DeepSeekRegexBuilder  # noqa: E402
from parseforge.pipeline import (  # noqa: E402
    LLMProviderConfig,
    TrialMetadata,
    run_command_pipeline,
)
from parseforge.sampling import DeviceConnection  # noqa: E402
from parseforge.sampling.backends import NetmikoSampler  # noqa: E402

pytestmark = pytest.mark.real

MODEL = "deepseek-v4-flash"

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def test_build_integration_clusters_real_trials(
    deepseek_key: str, cisco_sandbox_connection: DeviceConnection, tmp_path: Path
) -> None:
    naming_builder = DeepSeekRegexBuilder(api_key=deepseek_key, model=MODEL)
    generation_config = LLMProviderConfig(
        provider="deepseek", api_key=deepseek_key, model=MODEL
    )
    naming_index_path = tmp_path / ".cli-name.json"

    cli_name = None
    for _ in range(2):
        result = run_command_pipeline(
            "show clock",
            CONTEXT,
            cisco_sandbox_connection,
            naming_builder,
            NetmikoSampler(),
            generation_config,
            store_root=tmp_path,
            naming_index_path=naming_index_path,
            metadata=TrialMetadata(
                project="parseforge-integration-test",
                description="live integration-build test via DeepSeek",
            ),
        )
        assert result.passed is True
        cli_name = result.cli_name

    assert cli_name is not None
    key = paths.DeviceKey(
        vendor=CONTEXT.vendor, family=CONTEXT.family, os=CONTEXT.os, cli_name=cli_name
    )

    reference = build_integration(tmp_path, key)

    # Two real trials of the same command must cluster into at least one
    # group (real generations sharing an output schema get grouped
    # together), and can never split into more groups than trials.
    assert 1 <= len(reference) <= 2
    assert sum(group.group_case_count for group in reference.values()) == 2

    integration_dir = paths.integration_dir(tmp_path, key)
    reference_json = json.loads(
        (integration_dir / "reference.json").read_text(encoding="utf-8")
    )
    assert reference_json["total_case_count"] == 2
    assert list(integration_dir.glob("group*-template*.textfsm"))

    summary_path = write_reference_summary(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    case_key = key.relative_path().as_posix()
    assert case_key in summary["cases"]
    assert summary["cases"][case_key]["total_case_count"] == 2
