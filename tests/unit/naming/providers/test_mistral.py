from dataclasses import dataclass

import pytest

mistralai = pytest.importorskip(
    "mistralai", reason="mistralai is an optional extra (parseforge[mistral])"
)

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.mistral import (  # noqa: E402
    DEFAULT_MODEL,
    MistralRegexBuilder,
)


class _FakeHTTPResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {"content-type": "application/json"}


def _make_error(status_code: int, message: str = "boom") -> "mistralai.models.SDKError":
    """A real SDKError — Mistral's SDK raises this single class for every
    HTTP failure, distinguished by exc.raw_response.status_code rather than
    a family of named exception classes like OpenAI/Anthropic (see
    providers/mistral.py's _is_retryable)."""
    return mistralai.models.SDKError(message, _FakeHTTPResponse(status_code, message))


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


class _FakeChat:
    def __init__(self, reply_text: str, finish_reason: str = "stop") -> None:
        self.reply_text = reply_text
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> _FakeCompletionResponse:
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


class _FakeMistral:
    def __init__(self, api_key=None, finish_reason: str = "stop"):
        self.api_key = api_key
        self.chat = _FakeChat(r"show\s+version", finish_reason=finish_reason)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-key")
    fake = _FakeMistral()
    monkeypatch.setattr(mistralai, "Mistral", lambda **kw: fake)

    builder = MistralRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.chat.calls) == 1
    call = fake.chat.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"]
    assert call["max_tokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-key")
    fake = _FakeMistral()
    monkeypatch.setattr(mistralai, "Mistral", lambda **kw: fake)

    response = MistralRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 33
    assert response.usage.output_tokens == 9
    assert response.usage.total_tokens == 42
    assert response.reason == "stop"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-key")
    fake = _FakeMistral(finish_reason="length")
    monkeypatch.setattr(mistralai, "Mistral", lambda **kw: fake)

    response = MistralRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "length"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error(429, "slow down")

    fake = _FakeMistral()
    fake.chat.complete = _raise
    monkeypatch.setattr(mistralai, "Mistral", lambda **kw: fake)

    response = MistralRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason.startswith("LLM-ERROR-mistral_sdk-429-")
    assert response.content == ""


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error(400, "malformed")

    fake = _FakeMistral()
    fake.chat.complete = _raise
    monkeypatch.setattr(mistralai, "Mistral", lambda **kw: fake)

    with pytest.raises(mistralai.models.SDKError, match="malformed"):
        MistralRegexBuilder().build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key or touch the network —
    a cache-hit lookup never calls build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError("Mistral() should not be constructed eagerly")

    monkeypatch.setattr(mistralai, "Mistral", _boom)

    MistralRegexBuilder()  # must not raise


def test_api_key_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeMistral(**kwargs)

    monkeypatch.setattr(mistralai, "Mistral", _fake_ctor)

    builder = MistralRegexBuilder(api_key="sk-test-123")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {"api_key": "sk-test-123"}


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    builder = MistralRegexBuilder()

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "sk-env-key")
    fake = _FakeMistral()
    monkeypatch.setattr(mistralai, "Mistral", lambda **kw: fake)

    builder = MistralRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.chat.calls[0]
    assert call["max_tokens"] == 2048
    assert call["temperature"] == 0.1
