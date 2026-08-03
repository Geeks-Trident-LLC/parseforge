from dataclasses import dataclass

import pytest

azure_ai_inference = pytest.importorskip(
    "azure.ai.inference",
    reason="azure-ai-inference is an optional extra (parseforge[azure])",
)
from azure.core.exceptions import HttpResponseError  # noqa: E402

from parseforge.naming.llm import CliContext  # noqa: E402
from parseforge.naming.providers.azure import AzureRegexBuilder  # noqa: E402


class _FakeHttpResponse:
    def __init__(self, status_code: int, reason: str = "boom") -> None:
        self.status_code = status_code
        self.reason = reason


def _make_error(status_code: int, message: str = "boom") -> HttpResponseError:
    """A real HttpResponseError — the azure-ai-inference SDK raises this
    single class for every HTTP failure, distinguished by
    exc.status_code (derived from the underlying HTTP response) rather
    than a family of named exception classes (see providers/azure.py's
    _is_retryable)."""
    return HttpResponseError(message=message, response=_FakeHttpResponse(status_code))


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
class _FakeChatCompletionsResponse:
    choices: list
    usage: _FakeUsage


class _FakeChatCompletionsClient:
    def __init__(self, endpoint=None, credential=None, api_version=None) -> None:
        self.endpoint = endpoint
        self.credential = credential
        self.api_version = api_version
        self.finish_reason = "stop"
        self.reply_text = r"show\s+version"
        self.calls: list[dict] = []

    def complete(self, **kwargs) -> _FakeChatCompletionsResponse:
        self.calls.append(kwargs)
        return _FakeChatCompletionsResponse(
            choices=[
                _FakeChoice(
                    message=_FakeMessage(self.reply_text),
                    finish_reason=self.finish_reason,
                )
            ],
            usage=_FakeUsage(prompt_tokens=33, completion_tokens=9, total_tokens=42),
        )


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_API_KEY", "sk-env-key")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://my-resource.openai.azure.com")
    # Deliberately not shaped like a real model name (e.g. "gpt-4.1-...")
    # -- estimate_cost() does fuzzy family-matching on the model string,
    # and this test relies on genuinely falling through to its "unknown
    # (provider, model)" 0.0 fallback, not accidentally matching a real
    # OpenAI/etc. pricing family.
    monkeypatch.setenv("AZURE_DEPLOYMENT", "my-custom-deployment")
    monkeypatch.delenv("AZURE_API_VERSION", raising=False)


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeChatCompletionsClient):
    monkeypatch.setattr(azure_ai_inference, "ChatCompletionsClient", lambda **kw: fake)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake = _FakeChatCompletionsClient()
    _patch_client(monkeypatch, fake)

    builder = AzureRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert "show version" in call["messages"][0]["content"]
    assert call["max_tokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    fake = _FakeChatCompletionsClient()
    _patch_client(monkeypatch, fake)

    response = AzureRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 33
    assert response.usage.output_tokens == 9
    assert response.usage.total_tokens == 42
    # No public pricing table for a customer's own Azure deployment —
    # estimate_cost() falls back to 0.0, not an error.
    assert response.reason == "stop"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake = _FakeChatCompletionsClient()
    fake.finish_reason = "length"
    _patch_client(monkeypatch, fake)

    response = AzureRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "length"
    assert response.ready is False


def test_retryable_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)

    def _raise(**kwargs):
        raise _make_error(429, "slow down")

    fake = _FakeChatCompletionsClient()
    fake.complete = _raise
    _patch_client(monkeypatch, fake)

    response = AzureRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.reason.startswith("LLM-ERROR-azure_sdk-429-")
    assert response.content == ""


def test_non_retryable_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    def _raise(**kwargs):
        raise _make_error(400, "malformed")

    fake = _FakeChatCompletionsClient()
    fake.complete = _raise
    _patch_client(monkeypatch, fake)

    with pytest.raises(HttpResponseError):
        AzureRegexBuilder().build_pattern("show version", CONTEXT)


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require an API key/endpoint/
    deployment or touch the network — a cache-hit lookup never calls
    build_pattern at all (see resolver.cli_name)."""

    def _boom(**kwargs):
        raise AssertionError(
            "ChatCompletionsClient() should not be constructed eagerly"
        )

    monkeypatch.setattr(azure_ai_inference, "ChatCompletionsClient", _boom)

    AzureRegexBuilder()  # must not raise


def test_arguments_are_passed_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_API_VERSION", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeChatCompletionsClient(**kwargs)

    monkeypatch.setattr(azure_ai_inference, "ChatCompletionsClient", _fake_ctor)

    builder = AzureRegexBuilder(
        deployment="my-deployment",
        api_key="sk-test-123",
        endpoint="https://my-resource.openai.azure.com",
        api_version="2024-06-01",
    )
    builder.build_pattern("show version", CONTEXT)

    assert captured["endpoint"] == (
        "https://my-resource.openai.azure.com/openai/deployments/my-deployment"
    )
    assert captured["credential"].key == "sk-test-123"
    assert captured["api_version"] == "2024-06-01"


def test_endpoint_already_full_is_used_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeChatCompletionsClient(**kwargs)

    monkeypatch.setattr(azure_ai_inference, "ChatCompletionsClient", _fake_ctor)

    full_endpoint = (
        "https://my-resource.openai.azure.com/openai/deployments/already-full"
    )
    builder = AzureRegexBuilder(
        deployment="ignored-since-endpoint-is-already-full",
        api_key="sk-test-123",
        endpoint=full_endpoint,
        api_version="2024-06-01",
    )
    builder.build_pattern("show version", CONTEXT)

    assert captured["endpoint"] == full_endpoint


def test_api_version_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AZURE_API_VERSION", raising=False)
    captured = {}

    def _fake_ctor(**kwargs):
        captured.update(kwargs)
        return _FakeChatCompletionsClient(**kwargs)

    monkeypatch.setattr(azure_ai_inference, "ChatCompletionsClient", _fake_ctor)

    builder = AzureRegexBuilder(
        deployment="my-deployment",
        api_key="sk-test-123",
        endpoint="https://my-resource.openai.azure.com",
    )
    builder.build_pattern("show version", CONTEXT)

    assert captured["api_version"] == "2024-02-15-preview"


def test_missing_api_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    builder = AzureRegexBuilder()

    with pytest.raises(RuntimeError, match="AZURE_API_KEY"):
        builder.build_pattern("show version", CONTEXT)


def test_missing_endpoint_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("AZURE_ENDPOINT", raising=False)
    builder = AzureRegexBuilder()

    with pytest.raises(RuntimeError, match="AZURE_ENDPOINT"):
        builder.build_pattern("show version", CONTEXT)


def test_missing_deployment_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("AZURE_DEPLOYMENT", raising=False)
    builder = AzureRegexBuilder()

    with pytest.raises(RuntimeError, match="AZURE_DEPLOYMENT"):
        builder.build_pattern("show version", CONTEXT)


def test_kwargs_pass_through_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    fake = _FakeChatCompletionsClient()
    _patch_client(monkeypatch, fake)

    builder = AzureRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.calls[0]
    assert call["max_tokens"] == 2048
    assert call["temperature"] == 0.1
