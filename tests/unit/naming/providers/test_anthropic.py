from dataclasses import dataclass

import anthropic
import pytest

from parseforge.naming.llm import CliContext
from parseforge.naming.providers.anthropic import DEFAULT_MODEL, AnthropicRegexBuilder


def _make_error(name: str, message: str = "boom") -> anthropic.AnthropicError:
    """A dynamically-named AnthropicError subclass — real subclasses like
    RateLimitError require constructing an httpx.Response, which isn't
    worth the ceremony here; classification only cares about the class
    name (see providers/errors.py) and the except clause only checks
    isinstance against the shared AnthropicError base."""
    cls = type(name, (anthropic.AnthropicError,), {})
    return cls(message)


CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _FakeMessageResponse:
    content: list
    usage: _FakeUsage
    stop_reason: str


class _FakeMessages:
    def __init__(self, reply_text: str, stop_reason: str = "end_turn") -> None:
        self.reply_text = reply_text
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _FakeMessageResponse:
        self.calls.append(kwargs)
        return _FakeMessageResponse(
            content=[_FakeTextBlock(self.reply_text)],
            usage=_FakeUsage(input_tokens=42, output_tokens=7),
            stop_reason=self.stop_reason,
        )


class _FakeAnthropic:
    def __init__(self, api_key=None, stop_reason: str = "end_turn"):
        self.api_key = api_key
        self.messages = _FakeMessages(r"show\s+version", stop_reason=stop_reason)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropic()
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    builder = AnthropicRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.messages.calls) == 1
    call = fake.messages.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"]
    assert call["max_tokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropic()
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    response = AnthropicRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 42
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 49
    assert response.usage.estimated_cost > 0
    assert response.reason == "end_turn"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeAnthropic(stop_reason="max_tokens")
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    response = AnthropicRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "max_tokens"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(**kwargs):
        raise _make_error("RateLimitError", "slow down")

    fake = _FakeAnthropic()
    fake.messages.create = _raise
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    response = AnthropicRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason == "LLM-ERROR-rate_limit-slow down"
    assert response.content == ""
    assert response.usage.estimated_cost == 0.0


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**kwargs):
        raise _make_error("BadRequestError", "malformed")

    fake = _FakeAnthropic()
    fake.messages.create = _raise
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    with pytest.raises(anthropic.AnthropicError, match="malformed"):
        AnthropicRegexBuilder().build_pattern("show version", CONTEXT)


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


def test_kwargs_override_max_tokens_and_pass_through_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeAnthropic()
    monkeypatch.setattr(
        "parseforge.naming.providers.anthropic.Anthropic", lambda **kw: fake
    )

    builder = AnthropicRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.messages.calls[0]
    assert call["max_tokens"] == 2048
    assert call["temperature"] == 0.1
