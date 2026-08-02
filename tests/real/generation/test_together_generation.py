"""Live integration test for generation.generate() via textfsm-ai + Together.

Skipped by default — run with `pytest --real` and TOGETHER_API_KEY set.
Makes real calls to the Together API (costs tokens).
"""

from __future__ import annotations

import io

import pytest
import textfsm

from parseforge.generation import generate

pytestmark = pytest.mark.real

MODEL = "meta-llama/Llama-3.1-8B-Instruct-Turbo"

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


def test_generate_show_clock(together_key: str) -> None:
    result = generate(SAMPLE, "together", together_key, MODEL)

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
