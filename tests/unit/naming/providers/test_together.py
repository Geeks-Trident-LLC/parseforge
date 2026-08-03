from dataclasses import dataclass

import pytest

openai = pytest.importorskip(
    "openai", reason="openai is an optional extra (parseforge[together])"
)

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.together import (  # noqa: E402
    DEFAULT_MODEL,
    TogetherRegexBuilder,
)


def _make_error(name: str, message: str = "boom") -> openai.OpenAIError:
    """A dynamically-named OpenAIError subclass — real subclasses like
    RateLimitError require constructing an httpx.Response, which isn't
    worth the ceremony here; classification only cares about the class
    name (see providers/errors.py) and the except clause only checks
    isinstance against the shared OpenAIError base."""
    cls = type(name, (openai.OpenAIError,), {})
    return cls(message)


CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage
    finish_reason: str = "stop"


@dataclass
class _FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class _FakeCompletionResponse:
    choices: list
    usage: _FakeUsage


class _FakeCompletions:
    def __init__(self, reply_text: str, finish_reason: str = "stop") -> None:
        self.reply_text = reply_text
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    def create(self, **kwargs) -> _FakeCompletionResponse:
        self.calls.append(kwargs)
        return _FakeCompletionResponse(
            choices=[
                _FakeChoice(
                    message=_FakeMessage(self.reply_text),
                    finish_reason=self.finish_reason,
                )
            ],
            usage=_FakeUsage(prompt_tokens=33, completion_tokens=9, total_tokens=42),
        )


class _FakeChat:
    def __init__(self, reply_text: str, finish_reason: str = "stop") -> None:
        self.completions = _FakeCompletions(reply_text, finish_reason=finish_reason)


class _FakeOpenAI:
    def __init__(self, api_key=None, base_url=None, finish_reason: str = "stop"):
        self.api_key = api_key
        self.base_url = base_url
        self.chat = _FakeChat(r"show\s+version", finish_reason=finish_reason)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "sk-env-key")
    fake = _FakeOpenAI()
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: fake)

    builder = TogetherRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.chat.completions.calls) == 1
    call = fake.chat.completions.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"]
    assert call["max_tokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "sk-env-key")
    fake = _FakeOpenAI()
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: fake)

    response = TogetherRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 33
    assert response.usage.output_tokens == 9
    assert response.usage.total_tokens == 42
    assert response.reason == "stop"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "sk-env-key")
    fake = _FakeOpenAI(finish_reason="length")
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: fake)

    response = TogetherRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "length"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error("RateLimitError", "slow down")

    fake = _FakeOpenAI()
    fake.chat.completions.create = _raise
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: fake)

    response = TogetherRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason == "LLM-ERROR-rate_limit-slow down"
    assert response.content == ""


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error("BadRequestError", "malformed")

    fake = _FakeOpenAI()
    fake.chat.completions.create = _raise
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: fake)

    with pytest.raises(openai.OpenAIError, match="malformed"):
        TogetherRegexBuilder().build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key or touch the network —
    a cache-hit lookup never calls build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError("OpenAI() should not be constructed eagerly")

    monkeypatch.setattr(openai, "OpenAI", _boom)

    TogetherRegexBuilder()  # must not raise


def test_api_key_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeOpenAI(**kwargs)

    monkeypatch.setattr(openai, "OpenAI", _fake_ctor)

    builder = TogetherRegexBuilder(api_key="sk-test-123")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {
        "api_key": "sk-test-123",
        "base_url": "https://api.together.xyz/v1",
    }


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    builder = TogetherRegexBuilder()

    with pytest.raises(RuntimeError, match="TOGETHER_API_KEY"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "sk-env-key")
    fake = _FakeOpenAI()
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: fake)

    builder = TogetherRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.chat.completions.calls[0]
    assert call["max_tokens"] == 2048
    assert call["temperature"] == 0.1
