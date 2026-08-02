from dataclasses import dataclass, field
from typing import Any

import pytest

oci = pytest.importorskip("oci", reason="oci is an optional extra (parseforge[oci])")

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.oci import (  # noqa: E402
    DEFAULT_MODEL,
    OCIRegexBuilder,
)


def _make_error(status: int, code: str = "Error", message: str = "boom") -> Any:
    """A real ServiceError — the oci SDK raises this single class for
    every failed API call, distinguished by exc.status rather than a
    family of named exception classes (see providers/oci.py's
    _is_retryable)."""
    return oci.exceptions.ServiceError(
        status=status, code=code, headers={}, message=message
    )


CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


@dataclass
class _FakeTextContent:
    text: str


@dataclass
class _FakeMessage:
    content: list


@dataclass
class _FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class _FakeChoice:
    message: _FakeMessage
    finish_reason: str


@dataclass
class _FakeChatResponse:
    choices: list
    usage: Any = None


@dataclass
class _FakeChatResult:
    chat_response: _FakeChatResponse


@dataclass
class _FakeResponse:
    data: _FakeChatResult = field(default=None)  # type: ignore[assignment]


class _FakeClient:
    def __init__(self, reply_text: str, finish_reason: str = "stop") -> None:
        self.reply_text = reply_text
        self.finish_reason = finish_reason
        self.calls: list[Any] = []

    def chat(self, chat_details: Any) -> _FakeResponse:
        self.calls.append(chat_details)
        chat_response = _FakeChatResponse(
            choices=[
                _FakeChoice(
                    message=_FakeMessage(
                        content=[_FakeTextContent(text=self.reply_text)]
                    ),
                    finish_reason=self.finish_reason,
                )
            ],
            usage=_FakeUsage(prompt_tokens=42, completion_tokens=7, total_tokens=49),
        )
        return _FakeResponse(data=_FakeChatResult(chat_response=chat_response))


def _patch_config(
    monkeypatch: pytest.MonkeyPatch, region: str | None = "us-ashburn-1"
) -> None:
    config: dict[str, Any] = {}
    if region:
        config["region"] = region
    monkeypatch.setattr(oci.config, "from_file", lambda *a, **k: dict(config))


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(
        oci.generative_ai_inference, "GenerativeAiInferenceClient", lambda config: fake
    )


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    _patch_config(monkeypatch)
    fake = _FakeClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    builder = OCIRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.calls) == 1
    chat_details = fake.calls[0]
    assert chat_details.compartment_id == "ocid1.compartment.test"
    assert chat_details.serving_mode.model_id == DEFAULT_MODEL
    assert chat_details.chat_request.max_tokens >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    _patch_config(monkeypatch)
    fake = _FakeClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    response = OCIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 42
    assert response.usage.output_tokens == 7
    assert response.usage.total_tokens == 49
    assert response.usage.estimated_cost > 0
    assert response.reason == "stop"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    _patch_config(monkeypatch)
    fake = _FakeClient(r"show\s+version", finish_reason="length")
    _patch_client(monkeypatch, fake)

    response = OCIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "length"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    _patch_config(monkeypatch)

    def _raise(chat_details: Any) -> Any:
        raise _make_error(429, "TooManyRequests", "slow down")

    fake = _FakeClient(r"show\s+version")
    fake.chat = _raise
    _patch_client(monkeypatch, fake)

    response = OCIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason.startswith("LLM-ERROR-oci_sdk-429-")
    assert response.content == ""
    assert response.usage.estimated_cost == 0.0


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    _patch_config(monkeypatch)

    def _raise(chat_details: Any) -> Any:
        raise _make_error(400, "InvalidParameter", "malformed")

    fake = _FakeClient(r"show\s+version")
    fake.chat = _raise
    _patch_client(monkeypatch, fake)

    with pytest.raises(oci.exceptions.ServiceError):
        OCIRegexBuilder().build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require a compartment_id/region
    or touch the network — a cache-hit lookup never calls build_pattern at
    all (see resolver.cli_name)."""

    def _boom(config: Any) -> Any:
        raise AssertionError(
            "GenerativeAiInferenceClient() should not be constructed eagerly"
        )

    monkeypatch.setattr(
        oci.generative_ai_inference, "GenerativeAiInferenceClient", _boom
    )

    OCIRegexBuilder()  # must not raise


def test_compartment_id_and_region_argument_are_passed_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OCI_COMPARTMENT_ID", raising=False)
    monkeypatch.delenv("OCI_REGION", raising=False)
    _patch_config(monkeypatch, region=None)
    captured: dict[str, Any] = {}

    def _fake_ctor(config: Any) -> _FakeClient:
        captured.update(config)
        return _FakeClient(r"show\s+version")

    monkeypatch.setattr(
        oci.generative_ai_inference, "GenerativeAiInferenceClient", _fake_ctor
    )

    builder = OCIRegexBuilder(
        compartment_id="ocid1.compartment.test", region="us-phoenix-1"
    )
    builder.build_pattern("show version", CONTEXT)

    assert captured["region"] == "us-phoenix-1"


def test_compartment_id_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.from-env")
    _patch_config(monkeypatch)
    fake = _FakeClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    builder = OCIRegexBuilder()
    builder.build_pattern("show version", CONTEXT)

    assert fake.calls[0].compartment_id == "ocid1.compartment.from-env"


def test_region_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    monkeypatch.setenv("OCI_REGION", "eu-frankfurt-1")
    _patch_config(monkeypatch, region=None)
    captured: dict[str, Any] = {}

    def _fake_ctor(config: Any) -> _FakeClient:
        captured.update(config)
        return _FakeClient(r"show\s+version")

    monkeypatch.setattr(
        oci.generative_ai_inference, "GenerativeAiInferenceClient", _fake_ctor
    )

    OCIRegexBuilder().build_pattern("show version", CONTEXT)

    assert captured["region"] == "eu-frankfurt-1"


def test_region_falls_back_to_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    monkeypatch.delenv("OCI_REGION", raising=False)
    _patch_config(monkeypatch, region="ap-tokyo-1")
    fake = _FakeClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    response = OCIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is True


def test_missing_compartment_id_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OCI_COMPARTMENT_ID", raising=False)
    _patch_config(monkeypatch)
    builder = OCIRegexBuilder()

    with pytest.raises(RuntimeError, match="OCI_COMPARTMENT_ID"):
        builder.build_pattern("show version", CONTEXT)


def test_missing_region_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    monkeypatch.delenv("OCI_REGION", raising=False)
    _patch_config(monkeypatch, region=None)
    builder = OCIRegexBuilder()

    with pytest.raises(RuntimeError, match="OCI_REGION"):
        builder.build_pattern("show version", CONTEXT)


def test_config_file_error_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")

    def _boom(*a: Any, **k: Any) -> Any:
        raise oci.exceptions.ConfigFileNotFound("no config file")

    monkeypatch.setattr(oci.config, "from_file", _boom)
    builder = OCIRegexBuilder()

    with pytest.raises(RuntimeError, match="OCI config file"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCI_COMPARTMENT_ID", "ocid1.compartment.test")
    _patch_config(monkeypatch)
    fake = _FakeClient(r"show\s+version")
    _patch_client(monkeypatch, fake)

    builder = OCIRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    chat_details = fake.calls[0]
    assert chat_details.chat_request.max_tokens == 2048
    assert chat_details.chat_request.temperature == 0.1
