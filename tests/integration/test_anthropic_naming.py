"""Live-API integration tests for the Anthropic-backed naming pipeline.

Skipped by default — run with `pytest --real` and ANTHROPIC_API_KEY set.
Makes real calls to the Anthropic API (costs tokens).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from parseforge.naming import CliContext, cli_name
from parseforge.naming.assemble import pattern_to_cli_name
from parseforge.naming.providers.anthropic import AnthropicRegexBuilder

pytestmark = pytest.mark.integration

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def test_build_pattern_matches_its_own_command(anthropic_key: str) -> None:
    builder = AnthropicRegexBuilder(api_key=anthropic_key)
    pattern = builder.build_pattern("show version", CONTEXT)
    assert re.fullmatch(pattern, "show version")


def test_build_pattern_handles_a_variable_token(anthropic_key: str) -> None:
    builder = AnthropicRegexBuilder(api_key=anthropic_key)
    command = "show interface GE1.1 status"
    pattern = builder.build_pattern(command, CONTEXT)
    assert re.fullmatch(pattern, command)
    assert pattern_to_cli_name(pattern) == "show-interface-var1-status"


def test_cli_name_end_to_end_fixed_command(anthropic_key: str, tmp_path: Path) -> None:
    builder = AnthropicRegexBuilder(api_key=anthropic_key)
    index_path = tmp_path / ".cli-name.json"

    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)

    assert name == "show-version"
    assert index_path.exists()


def test_cli_name_end_to_end_is_cached_on_second_call(
    anthropic_key: str, tmp_path: Path
) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = AnthropicRegexBuilder(api_key=anthropic_key)

    cli_name("show clock", CONTEXT, builder=builder, index_path=index_path)

    # Second call for the same command must hit the on-disk cache, not the
    # LLM again — pass a builder that raises if it's ever called.
    def _boom(command: str, context: CliContext) -> str:
        raise AssertionError("cache hit should not call the LLM")

    class _FailingBuilder:
        build_pattern = staticmethod(_boom)

    name = cli_name(
        "show clock", CONTEXT, builder=_FailingBuilder(), index_path=index_path
    )
    assert name == "show-clock"
