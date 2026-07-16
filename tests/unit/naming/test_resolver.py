from pathlib import Path

import pytest

from parseforge.naming.cache import NameIndex
from parseforge.naming.llm import CliContext
from parseforge.naming.resolver import cli_name

CONTEXT = CliContext(vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1")


class FakeRegexBuilder:
    """Records calls so tests can assert the LLM is only used on a cache miss."""

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.calls = 0

    def build_pattern(self, command: str, context: CliContext) -> str:
        self.calls += 1
        return self.pattern


def test_cache_miss_calls_builder_and_persists(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"(?i)show\s+version")

    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)

    assert name == "show-version"
    assert builder.calls == 1
    assert NameIndex(index_path).match("show version") == "show-version"


def test_cache_hit_does_not_call_builder(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"(?i)show\s+version")

    cli_name("show version", CONTEXT, builder=builder, index_path=index_path)
    assert builder.calls == 1

    # Second call for the same command must hit the on-disk cache, not the LLM.
    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)
    assert name == "show-version"
    assert builder.calls == 1


def test_pattern_that_does_not_match_its_own_command_raises(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"(?i)show\s+clock")

    with pytest.raises(ValueError):
        cli_name("show version", CONTEXT, builder=builder, index_path=index_path)
