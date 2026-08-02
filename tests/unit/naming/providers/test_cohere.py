from dataclasses import dataclass

import pytest

cohere = pytest.importorskip(
    "cohere", reason="cohere is an optional extra (parseforge[cohere])"
)
from cohere.core.api_error import ApiError  # noqa: E402

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.cohere import (  # noqa: E402
    DEFAULT_MODEL,
    CohereRegexBuilder,
)


def _make_error(status_code: int, message: str = "boom") -> ApiError:
    """A real ApiError — every named cohere SDK exception (BadRequestError,
    UnauthorizedError, ...) is a thin subclass that sets status_code in its
    own __init__, so constructing the shared base directly with a given
    status_code is equivalent for classification purposes (see
    providers/cohere.py's _is_retryable)."""
    return ApiError(status_code=status_code, body=message)


CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


@dataclass
class _FakeTextBlock:
    text: str


@dataclass
class _FakeMessage:
    content: list


@dataclass
class _FakeUsageTokens:
    input_tokens: float
    output_tokens: float


@dataclass
class _FakeUsage:
    tokens: _FakeUsageTokens


@dataclass
class _FakeChatResponse:
    message: _FakeMessage
    usage: _FakeUsage
    finish_reason: str = "COMPLETE"


class _FakeClientV2:
    def __init__(self, api_key=None, finish_reason: str = "COMPLETE") -> None:
        self.api_key = api_key
        self.finish_reason = finish_reason
        self.reply_text = r"show\s+version"
        self.calls: list[dict] = []

    def chat(self, **kwargs) -> _FakeChatResponse:
        self.calls.append(kwargs)
        return _FakeChatResponse(
            message=_FakeMessage(content=[_FakeTextBlock(self.reply_text)]),
            usage=_FakeUsage(tokens=_FakeUsageTokens(input_tokens=33, output_tokens=9)),
            finish_reason=self.finish_reason,
        )


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "sk-env-key")
    fake = _FakeClientV2()
    monkeypatch.setattr(cohere, "ClientV2", lambda **kw: fake)

    builder = CohereRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"]
    assert call["max_tokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "sk-env-key")
    fake = _FakeClientV2()
    monkeypatch.setattr(cohere, "ClientV2", lambda **kw: fake)

    response = CohereRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 33
    assert response.usage.output_tokens == 9
    # Cohere's usage.tokens has no total_tokens field — it's computed as
    # input + output rather than read off the response.
    assert response.usage.total_tokens == 42
    assert response.usage.estimated_cost > 0
    assert response.reason == "COMPLETE"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "sk-env-key")
    fake = _FakeClientV2(finish_reason="MAX_TOKENS")
    monkeypatch.setattr(cohere, "ClientV2", lambda **kw: fake)

    response = CohereRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "MAX_TOKENS"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error(429, "slow down")

    fake = _FakeClientV2()
    fake.chat = _raise
    monkeypatch.setattr(cohere, "ClientV2", lambda **kw: fake)

    response = CohereRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason.startswith("LLM-ERROR-cohere_sdk-429-")
    assert response.content == ""
    assert response.usage.estimated_cost == 0.0


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error(400, "malformed")

    fake = _FakeClientV2()
    fake.chat = _raise
    monkeypatch.setattr(cohere, "ClientV2", lambda **kw: fake)

    with pytest.raises(ApiError):
        CohereRegexBuilder().build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key or touch the network —
    a cache-hit lookup never calls build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError("ClientV2() should not be constructed eagerly")

    monkeypatch.setattr(cohere, "ClientV2", _boom)

    CohereRegexBuilder()  # must not raise


def test_api_key_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeClientV2(**kwargs)

    monkeypatch.setattr(cohere, "ClientV2", _fake_ctor)

    builder = CohereRegexBuilder(api_key="sk-test-123")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {"api_key": "sk-test-123"}


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COHERE_API_KEY", raising=False)
    builder = CohereRegexBuilder()

    with pytest.raises(RuntimeError, match="COHERE_API_KEY"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "sk-env-key")
    fake = _FakeClientV2()
    monkeypatch.setattr(cohere, "ClientV2", lambda **kw: fake)

    builder = CohereRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.calls[0]
    assert call["max_tokens"] == 2048
    assert call["temperature"] == 0.1
