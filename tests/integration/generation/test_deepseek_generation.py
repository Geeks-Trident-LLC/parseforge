"""Live integration test for generation.generate() via textfsm-ai + DeepSeek.

Skipped by default — run with `pytest --real` and DEEPSEEK_API_KEY set.
Makes real calls to the DeepSeek API (costs tokens).
"""

from __future__ import annotations

import io

import pytest
import textfsm

from parseforge.generation import generate

pytestmark = pytest.mark.integration

MODEL = "deepseek-v4-flash"

# Real "show clock" output from a Cisco IOS/IOS-XE device.
SAMPLE = "*17:42:39.125 UTC Fri Jul 17 2026"


def test_generate_show_clock(deepseek_key: str) -> None:
    result = generate(SAMPLE, "deepseek", deepseek_key, MODEL)

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
