"""Live-API integration tests for the Amazon Bedrock-backed naming pipeline.

Skipped by default — run with `pytest --real` and BEDROCK_REGION set (plus
AWS credentials configured via the usual chain: env vars, ~/.aws/credentials,
or an IAM role). Makes real calls to Bedrock (costs tokens).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from parseforge.naming import BedrockRegexBuilder, CliContext, cli_name
from parseforge.naming.assemble import pattern_to_cli_name

pytestmark = pytest.mark.real

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def test_build_pattern_matches_its_own_command(bedrock_region: str) -> None:
    builder = BedrockRegexBuilder(region=bedrock_region)
    response = builder.build_pattern("show version", CONTEXT)
    assert response.ready
    assert re.fullmatch(response.content, "show version", re.I)


def test_build_pattern_handles_a_variable_token(bedrock_region: str) -> None:
    builder = BedrockRegexBuilder(region=bedrock_region)
    command = "show interface GE1.1 status"
    response = builder.build_pattern(command, CONTEXT)
    assert response.ready
    assert re.fullmatch(response.content, command, re.I)
    assert pattern_to_cli_name(response.content) == "show-interface-var1-status"


def test_cli_name_end_to_end_fixed_command(bedrock_region: str, tmp_path: Path) -> None:
    builder = BedrockRegexBuilder(region=bedrock_region)
    index_path = tmp_path / ".cli-name.json"

    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)

    assert name == "show-version"
    assert index_path.exists()


def test_cli_name_end_to_end_is_cached_on_second_call(
    bedrock_region: str, tmp_path: Path
) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = BedrockRegexBuilder(region=bedrock_region)

    cli_name("show clock", CONTEXT, builder=builder, index_path=index_path)

    # Second call for the same command must hit the on-disk cache, not the
    # LLM again — pass a builder that raises if it's ever called.
    def _boom(command: str, context: CliContext, **kwargs: Any):
        raise AssertionError("cache hit should not call the LLM")

    class _FailingBuilder:
        build_pattern = staticmethod(_boom)

    name = cli_name(
        "show clock", CONTEXT, builder=_FailingBuilder(), index_path=index_path
    )
    assert name == "show-clock"
