from typing import Any

import pytest

boto3 = pytest.importorskip(
    "boto3", reason="boto3 is an optional extra (parseforge[bedrock])"
)
from botocore.exceptions import ClientError  # noqa: E402

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.bedrock import (  # noqa: E402
    DEFAULT_MODEL,
    BedrockRegexBuilder,
)


def _make_error(code: str, message: str = "boom") -> ClientError:
    """A dynamically-named ClientError subclass — real Bedrock exception
    classes (ValidationException, ThrottlingException, ...) are generated
    per-client by botocore, so they can't be referenced directly here;
    classification only cares about the class name (see
    providers/bedrock.py's _is_retryable)."""
    cls = type(code, (ClientError,), {})
    return cls(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="Converse",
    )


CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


class _FakeBedrockClient:
    def __init__(self, reply_text: str, stop_reason: str = "end_turn") -> None:
        self.reply_text = reply_text
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def converse(self, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        return {
            "output": {"message": {"content": [{"text": self.reply_text}]}},
            "usage": {
                "inputTokens": 42,
                "outputTokens": 7,
                "totalTokens": 49,
            },
            "stopReason": self.stop_reason,
        }


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeBedrockClient) -> None:
    monkeypatch.setattr(boto3, "client", lambda *a, **kw: fake)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeBedrockClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    builder = BedrockRegexBuilder(region="us-east-1")
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["modelId"] == DEFAULT_MODEL
    assert "show version" in call["messages"][0]["content"][0]["text"]
    assert call["inferenceConfig"]["maxTokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeBedrockClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    response = BedrockRegexBuilder(region="us-east-1").build_pattern(
        "show version", CONTEXT
    )

    assert response.usage.input_tokens == 42
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 49
    assert response.reason == "end_turn"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBedrockClient(r"show\s+version", stop_reason="max_tokens")
    _patch_client(monkeypatch, fake)

    response = BedrockRegexBuilder(region="us-east-1").build_pattern(
        "show version", CONTEXT
    )

    assert response.reason == "max_tokens"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(**kwargs):
        raise _make_error("ThrottlingException", "slow down")

    fake = _FakeBedrockClient(r"show\s+version")
    fake.converse = _raise
    _patch_client(monkeypatch, fake)

    response = BedrockRegexBuilder(region="us-east-1").build_pattern(
        "show version", CONTEXT
    )

    assert response.ready is False
    assert response.reason.startswith("LLM-ERROR-bedrock_sdk-ThrottlingException-")
    assert response.content == ""


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(**kwargs):
        raise _make_error("ValidationException", "malformed")

    fake = _FakeBedrockClient(r"show\s+version")
    fake.converse = _raise
    _patch_client(monkeypatch, fake)

    with pytest.raises(ClientError, match="malformed"):
        BedrockRegexBuilder(region="us-east-1").build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require a region or touch the
    network — a cache-hit lookup never calls build_pattern at all (see
    resolver.cli_name)."""

    def _boom(*a, **kwargs):
        raise AssertionError("boto3.client() should not be constructed eagerly")

    monkeypatch.setattr(boto3, "client", _boom)

    BedrockRegexBuilder()  # must not raise


def test_region_argument_is_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_DEFAULT_REGION", raising=False)
    captured = {}

    def _fake_ctor(*a, **kwargs):
        captured.update(kwargs)
        return _FakeBedrockClient(r"show\s+version")

    monkeypatch.setattr(boto3, "client", _fake_ctor)

    builder = BedrockRegexBuilder(region="us-west-2")
    builder.build_pattern("show version", CONTEXT)

    assert captured == {"region_name": "us-west-2"}


def test_region_falls_back_to_bedrock_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BEDROCK_REGION", "eu-west-1")
    monkeypatch.delenv("BEDROCK_DEFAULT_REGION", raising=False)
    captured = {}

    def _fake_ctor(*a, **kwargs):
        captured.update(kwargs)
        return _FakeBedrockClient(r"show\s+version")

    monkeypatch.setattr(boto3, "client", _fake_ctor)

    BedrockRegexBuilder().build_pattern("show version", CONTEXT)

    assert captured["region_name"] == "eu-west-1"


def test_region_falls_back_to_bedrock_default_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.setenv("BEDROCK_DEFAULT_REGION", "ap-southeast-1")
    captured = {}

    def _fake_ctor(*a, **kwargs):
        captured.update(kwargs)
        return _FakeBedrockClient(r"show\s+version")

    monkeypatch.setattr(boto3, "client", _fake_ctor)

    BedrockRegexBuilder().build_pattern("show version", CONTEXT)

    assert captured["region_name"] == "ap-southeast-1"


def test_missing_region_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEDROCK_REGION", raising=False)
    monkeypatch.delenv("BEDROCK_DEFAULT_REGION", raising=False)
    builder = BedrockRegexBuilder()

    with pytest.raises(RuntimeError, match="BEDROCK_REGION"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeBedrockClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    builder = BedrockRegexBuilder(region="us-east-1")
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.calls[0]
    assert call["inferenceConfig"]["maxTokens"] == 2048
    assert call["inferenceConfig"]["temperature"] == 0.1
