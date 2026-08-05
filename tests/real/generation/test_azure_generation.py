"""Live integration test for generation.generate() via textfsm-ai + Azure.

Skipped by default — run with `pytest --real` and AZURE_API_KEY/
AZURE_ENDPOINT/AZURE_DEPLOYMENT set. Makes real calls to the caller's own
Azure resource (costs tokens).
"""

from __future__ import annotations

import io
import os

import pytest
import textfsm

from parseforge.generation import generate
from parseforge.naming.providers.anyask_builder import DEFAULT_API_VERSION

pytestmark = pytest.mark.real

# Real "show clock" output from a Cisco IOS/IOS-XE device, plus a
# "SAMPLE REFERENCE SOURCE" annotation describing it. Note: textfsm-ai's
# own prompt has no closing delimiter on its Sample section, so this
# annotation isn't guaranteed to be excluded from the generated
# template — see the discussion around this file's history.
SAMPLE = """
*17:42:39.125 UTC Fri Jul 17 2026

SAMPLE REFERENCE SOURCE
=============================
a real "show clock" output from a Cisco IOS/IOS-XE device
"""


def test_generate_show_clock(
    azure_key: str, azure_endpoint: str, azure_deployment: str
) -> None:
    # textfsm-ai's own azure special-case reads `deployment` off the
    # positional `model` argument (see generation_engine.run()) —
    # parseforge.generation.generate() forwards **kwargs straight through
    # to run_pipeline(), so endpoint/api_version pass through unchanged.
    # api_version has no from_env()-style fallback on this path (unlike
    # naming's AzureRegexBuilder), so it must be supplied explicitly here,
    # same as cli/main.py's generate_template_cmd/pipeline.py do.
    result = generate(
        SAMPLE,
        "azure",
        azure_key,
        azure_deployment,
        endpoint=azure_endpoint,
        api_version=os.environ.get("AZURE_API_VERSION", DEFAULT_API_VERSION),
    )

    assert result.ready, result.reason
    assert result.template.strip()
    assert result.readable_dsl.strip()
    assert result.recognizers
    assert result.usage.total_tokens > 0
    assert result.duration_ms > 0

    # The generated template must actually parse the sample it was built
    # from — this is the real end-to-end check, not just "did we get text
    # back." One line of show clock output should produce exactly one
    # record.
    fsm = textfsm.TextFSM(io.StringIO(result.template))
    records = fsm.ParseText(SAMPLE)
    assert len(records) == 1
