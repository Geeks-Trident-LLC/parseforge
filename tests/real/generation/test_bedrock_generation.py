"""Live integration test for generation.generate() via textfsm-ai + Amazon Bedrock.

Skipped by default — run with `pytest --real` and BEDROCK_REGION set (plus
AWS credentials configured via the usual chain: env vars,
~/.aws/credentials, or an IAM role). Makes real calls to Bedrock (costs
tokens).
"""

from __future__ import annotations

import io

import pytest
import textfsm

from parseforge.generation import generate

pytestmark = pytest.mark.real

MODEL = "anthropic.claude-haiku-4-5-v1:0"

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


def test_generate_show_clock(bedrock_region: str) -> None:
    # No API key for bedrock (see naming/providers/bedrock.py) —
    # generation.generate()'s api_key positional arg is still required by
    # its signature, but textfsm-ai's own generation_engine.run() never
    # reads it for this provider, so an empty string is harmless. Its
    # kwarg is named "region" (shared with vertexai/oci), not "location".
    result = generate(
        SAMPLE,
        "bedrock",
        "",
        MODEL,
        region=bedrock_region,
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
