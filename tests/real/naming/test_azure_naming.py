"""Live-API integration tests for the Azure OpenAI-backed naming pipeline.

Skipped by default — run with `pytest --real` and AZURE_API_KEY/
AZURE_ENDPOINT/AZURE_DEPLOYMENT set. Makes real calls to the caller's own
Azure resource (costs tokens).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from parseforge.naming import CliContext, cli_name
from parseforge.naming.assemble import pattern_to_cli_name
from parseforge.naming.providers.azure import AzureRegexBuilder

pytestmark = pytest.mark.real

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def test_build_pattern_matches_its_own_command(
    azure_key: str, azure_endpoint: str, azure_deployment: str
) -> None:
    builder = AzureRegexBuilder(
        deployment=azure_deployment, api_key=azure_key, endpoint=azure_endpoint
    )
    response = builder.build_pattern("show version", CONTEXT)
    assert response.ready
    assert re.fullmatch(response.content, "show version", re.I)


def test_build_pattern_handles_a_variable_token(
    azure_key: str, azure_endpoint: str, azure_deployment: str
) -> None:
    builder = AzureRegexBuilder(
        deployment=azure_deployment, api_key=azure_key, endpoint=azure_endpoint
    )
    command = "show interface GE1.1 status"
    response = builder.build_pattern(command, CONTEXT)
    assert response.ready
    assert re.fullmatch(response.content, command, re.I)
    assert pattern_to_cli_name(response.content) == "show-interface-var1-status"


def test_cli_name_end_to_end_fixed_command(
    azure_key: str, azure_endpoint: str, azure_deployment: str, tmp_path: Path
) -> None:
    builder = AzureRegexBuilder(
        deployment=azure_deployment, api_key=azure_key, endpoint=azure_endpoint
    )
    index_path = tmp_path / ".cli-name.json"

    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)

    assert name == "show-version"
    assert index_path.exists()


def test_cli_name_end_to_end_is_cached_on_second_call(
    azure_key: str, azure_endpoint: str, azure_deployment: str, tmp_path: Path
) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = AzureRegexBuilder(
        deployment=azure_deployment, api_key=azure_key, endpoint=azure_endpoint
    )

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
