"""Live integration test for generation.generate() via textfsm-ai + OCI
Generative AI.

Skipped by default — run with `pytest --real` and OCI_COMPARTMENT_ID/
OCI_REGION set (plus a valid ~/.oci/config with a DEFAULT profile). Makes
real calls to OCI Generative AI (costs money).
"""

from __future__ import annotations

import io

import pytest
import textfsm

from parseforge.generation import generate

pytestmark = pytest.mark.real

MODEL = "meta.llama-3.3-70b-instruct"

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


def test_generate_show_clock(oci_compartment_id: str, oci_region: str) -> None:
    # No API key for oci (see naming/providers/oci.py) —
    # generation.generate()'s api_key positional arg is still required by
    # its signature, but textfsm-ai's own generation_engine.run() never
    # reads it for this provider, so an empty string is harmless. region
    # is the kwarg shared with vertexai/bedrock; compartment_id has its
    # own dedicated kwarg (see pipeline.py's LLMProviderConfig docstring).
    result = generate(
        SAMPLE,
        "oci",
        "",
        MODEL,
        region=oci_region,
        compartment_id=oci_compartment_id,
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
