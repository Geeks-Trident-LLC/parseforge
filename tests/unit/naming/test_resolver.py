from pathlib import Path
from typing import Any

import pytest

from parseforge.naming.cache import NameIndex
from parseforge.naming.llm import CliContext, LLMCLIResponse, TokenUsage
from parseforge.naming.resolver import cli_name

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


def _response(content: str, ready: bool = True, reason: str = "stop") -> LLMCLIResponse:
    return LLMCLIResponse(
        content=content,
        raw=None,
        usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        duration_ms=1.0,
        reason=reason,
        ready=ready,
    )


class FakeRegexBuilder:
    """Records calls so tests can assert the LLM is only used on a cache miss."""

    def __init__(self, pattern: str, ready: bool = True, reason: str = "stop") -> None:
        self.pattern = pattern
        self.ready = ready
        self.reason = reason
        self.calls = 0
        self.last_kwargs: dict[str, Any] | None = None

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        self.calls += 1
        self.last_kwargs = kwargs
        return _response(self.pattern, ready=self.ready, reason=self.reason)


def test_cache_miss_calls_builder_and_persists(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"show\s+version")

    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)

    assert name == "show-version"
    assert builder.calls == 1
    assert NameIndex(index_path).match("show version") == "show-version"


def test_cache_hit_does_not_call_builder(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"show\s+version")

    cli_name("show version", CONTEXT, builder=builder, index_path=index_path)
    assert builder.calls == 1

    # Second call for the same command must hit the on-disk cache, not the LLM.
    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)
    assert name == "show-version"
    assert builder.calls == 1


def test_pattern_that_does_not_match_its_own_command_raises(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"show\s+clock")

    with pytest.raises(ValueError):
        cli_name("show version", CONTEXT, builder=builder, index_path=index_path)


def test_builder_output_is_normalized_before_caching(tmp_path: Path) -> None:
    """A builder returning mixed-case fixed text must still validate (matching
    is case-insensitive) and get stored in lowercase-normalized form."""
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"Show\s+Version")

    name = cli_name("show version", CONTEXT, builder=builder, index_path=index_path)

    assert name == "show-version"
    index = NameIndex(index_path)
    assert index._entries["show-version"] == r"show\s+version"


def test_not_ready_response_raises_instead_of_using_truncated_pattern(
    tmp_path: Path,
) -> None:
    """A response cut off before completing (e.g. hit max_tokens) must be
    rejected outright, not silently treated as a valid (possibly empty or
    partial) pattern."""
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder("", ready=False, reason="length")

    with pytest.raises(ValueError, match="length"):
        cli_name("show version", CONTEXT, builder=builder, index_path=index_path)


def test_kwargs_pass_through_to_builder(tmp_path: Path) -> None:
    index_path = tmp_path / ".cli-name.json"
    builder = FakeRegexBuilder(r"show\s+version")

    cli_name(
        "show version",
        CONTEXT,
        builder=builder,
        index_path=index_path,
        max_tokens=2048,
        temperature=0.1,
    )

    assert builder.last_kwargs == {"max_tokens": 2048, "temperature": 0.1}
