from dataclasses import dataclass

import pytest

from parseforge.naming.llm import CliContext
from parseforge.naming.providers.anthropic import DEFAULT_MODEL, AnthropicRegexBuilder

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


class _FakeMessages:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return type("Resp", (), {"content": [_FakeTextBlock(self.reply_text)]})()


class _FakeAnthropic:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.messages = _FakeMessages(r"show\s+version")


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropic()
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    builder = AnthropicRegexBuilder()
    pattern = builder.build_pattern("show version", CONTEXT)

    assert pattern == r"show\s+version"
    assert len(fake.messages.calls) == 1
    call = fake.messages.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"]


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key or touch the network —
    a cache-hit lookup never calls build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError("Anthropic() should not be constructed eagerly")

    monkeypatch.setattr("parseforge.naming.providers.anthropic.Anthropic", _boom)

    AnthropicRegexBuilder()  # must not raise


def test_api_key_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeAnthropic(**kwargs)

    monkeypatch.setattr("parseforge.naming.providers.anthropic.Anthropic", _fake_ctor)

    builder = AnthropicRegexBuilder(api_key="sk-test-123")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {"api_key": "sk-test-123"}
