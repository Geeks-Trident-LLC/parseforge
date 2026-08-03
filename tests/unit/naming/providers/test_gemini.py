from dataclasses import dataclass, field
from typing import Any

import pytest

genai = pytest.importorskip(
    "google.genai", reason="google-genai is an optional extra (parseforge[gemini])"
)

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.gemini import (  # noqa: E402
    DEFAULT_MODEL,
    GeminiRegexBuilder,
)


def _make_error(code: int, message: str = "boom") -> "genai.errors.APIError":
    """A real APIError — the google-genai SDK raises this single class for
    every HTTP failure, distinguished by exc.code rather than a family of
    named exception classes (see providers/gemini.py's _is_retryable)."""
    return genai.errors.APIError(
        code=code, response_json={"error": {"message": message}}
    )


CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


@dataclass
class _FakeUsageMetadata:
    prompt_token_count: int
    candidates_token_count: int
    total_token_count: int


@dataclass
class _FakeCandidate:
    finish_reason: Any


@dataclass
class _FakeGenerateContentResponse:
    text: str
    candidates: list = field(default_factory=list)
    usage_metadata: Any = None


class _FakeModels:
    def __init__(self, reply_text: str, finish_reason: Any) -> None:
        self.reply_text = reply_text
        self.finish_reason = finish_reason
        self.calls: list[dict] = []

    def generate_content(self, **kwargs: Any) -> _FakeGenerateContentResponse:
        self.calls.append(kwargs)
        return _FakeGenerateContentResponse(
            text=self.reply_text,
            candidates=[_FakeCandidate(finish_reason=self.finish_reason)],
            usage_metadata=_FakeUsageMetadata(
                prompt_token_count=33, candidates_token_count=9, total_token_count=42
            ),
        )


class _FakeClient:
    def __init__(self, api_key: Any = None, finish_reason: Any = None) -> None:
        self.api_key = api_key
        self.models = _FakeModels(
            r"show\s+version", finish_reason or genai.types.FinishReason.STOP
        )


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(genai, "Client", lambda **kw: fake)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env-key")
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    builder = GeminiRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.models.calls) == 1
    call = fake.models.calls[0]
    assert call["model"] == DEFAULT_MODEL
    assert "show version" in call["contents"]
    assert call["config"].max_output_tokens >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env-key")
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    response = GeminiRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 33
    assert response.usage.output_tokens == 9
    assert response.usage.total_tokens == 42
    # finish_reason is a str-subclassed enum -- reason should be the
    # plain value ("STOP"), not e.g. "FinishReason.STOP".
    assert response.reason == "STOP"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env-key")
    fake = _FakeClient(finish_reason=genai.types.FinishReason.MAX_TOKENS)
    _patch_client(monkeypatch, fake)

    response = GeminiRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "MAX_TOKENS"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error(429, "slow down")

    fake = _FakeClient()
    fake.models.generate_content = _raise
    _patch_client(monkeypatch, fake)

    response = GeminiRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason.startswith("LLM-ERROR-gemini_sdk-429-")
    assert response.content == ""


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env-key")

    def _raise(**kwargs):
        raise _make_error(400, "malformed")

    fake = _FakeClient()
    fake.models.generate_content = _raise
    _patch_client(monkeypatch, fake)

    with pytest.raises(genai.errors.APIError):
        GeminiRegexBuilder().build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key or touch the network —
    a cache-hit lookup never calls build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError("Client() should not be constructed eagerly")

    monkeypatch.setattr(genai, "Client", _boom)

    GeminiRegexBuilder()  # must not raise


def test_api_key_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeClient(**kwargs)

    monkeypatch.setattr(genai, "Client", _fake_ctor)

    builder = GeminiRegexBuilder(api_key="sk-test-123")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {"api_key": "sk-test-123"}


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    builder = GeminiRegexBuilder()

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "sk-env-key")
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    builder = GeminiRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.models.calls[0]
    assert call["config"].max_output_tokens == 2048
    assert call["config"].temperature == 0.1
