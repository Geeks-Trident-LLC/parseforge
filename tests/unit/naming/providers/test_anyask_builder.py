"""Tests for the generic anyask-backed RegexBuilder (replaces one
mock-a-different-raw-SDK test file per provider — all 18
``<Provider>RegexBuilder`` subclasses share this same code path now, so
only construction-kwarg mapping/provider-specific defaults need per-class
coverage; the core build_pattern() flow is tested once against the
generic base class."""

from __future__ import annotations

import anyask
import pytest

from parseforge.naming.llm import CliContext
from parseforge.naming.providers import anyask_builder as ab

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)


class _FakeProvider:
    def __init__(self, response=None, exc=None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    def generate_sync(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        if self._exc is not None:
            raise self._exc
        return self._response


def _ask_response(
    content="```\nshow\\s+version\n```",
    finish_reason="stop",
    prompt_tokens=33,
    completion_tokens=9,
    total_tokens=42,
    raw=None,
) -> anyask.AskResponse:
    return anyask.AskResponse(
        content=content,
        usage=anyask.TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
        finish_reason=finish_reason,
        provider="openai",
        model="gpt-4o-mini",
        raw=raw or object(),
    )


def _patch_get_provider(monkeypatch: pytest.MonkeyPatch, fake: _FakeProvider) -> None:
    monkeypatch.setattr(ab.anyask, "get_provider", lambda provider, **kw: fake)


def test_build_pattern_calls_client_and_extracts_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeProvider(_ask_response())
    _patch_get_provider(monkeypatch, fake)

    builder = ab.OpenAIRegexBuilder()
    response = builder.build_pattern("show version", CONTEXT)

    assert response.content == r"show\s+version"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == ab.default_model("openai")
    assert "show version" in call["prompt"]
    assert call["max_tokens"] >= 1024


def test_response_carries_usage_reason_and_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeProvider(_ask_response())
    _patch_get_provider(monkeypatch, fake)

    response = ab.OpenAIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.usage.input_tokens == 33
    assert response.usage.output_tokens == 9
    assert response.usage.total_tokens == 42
    assert response.reason == "stop"
    assert response.ready is True
    assert response.raw is not None
    assert response.duration_ms >= 0


def test_truncated_response_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProvider(_ask_response(finish_reason="length"))
    _patch_get_provider(monkeypatch, fake)

    response = ab.OpenAIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "length"
    assert response.ready is False


def test_missing_finish_reason_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProvider(_ask_response(finish_reason=None))
    _patch_get_provider(monkeypatch, fake)

    response = ab.OpenAIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False


def test_enum_like_finish_reason_uses_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini/Vertex AI's finish_reason is a str-subclassed enum whose own
    __str__ prints "FinishReason.STOP" rather than "STOP" -- confirm the
    generic builder reads .value off anything that has one, same as the
    old gemini.py/vertexai.py builders did."""

    class _FinishReason:
        value = "STOP"

        def __str__(self) -> str:  # pragma: no cover - guards against regressions
            return "FinishReason.STOP"

    fake = _FakeProvider(_ask_response(finish_reason=_FinishReason()))
    _patch_get_provider(monkeypatch, fake)

    response = ab.GeminiRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.reason == "STOP"
    assert response.ready is True


def test_provider_error_returns_not_ready_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cause = RuntimeError("slow down")
    error = anyask.ProviderError("slow down")
    error.__cause__ = cause  # mirrors anyask's own `raise ProviderError(...) from exc`
    fake = _FakeProvider(exc=error)
    _patch_get_provider(monkeypatch, fake)

    response = ab.OpenAIRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.content == ""
    assert "RuntimeError" in response.reason
    assert "slow down" in response.reason


def test_provider_auth_error_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ProviderAuthError is a ProviderError subclass, so it's caught the
    same way -- returned as a not-ready response, never propagated."""
    fake = _FakeProvider(exc=anyask.ProviderAuthError("no api key"))
    _patch_get_provider(monkeypatch, fake)

    response = ab.AnthropicRegexBuilder().build_pattern("show version", CONTEXT)

    assert response.ready is False
    assert response.content == ""


def test_client_is_constructed_lazily(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instantiating the builder must not require credentials or touch the
    network -- a cache-hit lookup never calls build_pattern at all (see
    resolver.cli_name)."""

    def _boom(provider, **kw):
        raise AssertionError("anyask.get_provider() should not be called eagerly")

    monkeypatch.setattr(ab.anyask, "get_provider", _boom)

    ab.OpenAIRegexBuilder()  # must not raise


def test_client_is_cached_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def _get_provider(provider, **kw):
        calls.append(provider)
        return _FakeProvider(_ask_response())

    monkeypatch.setattr(ab.anyask, "get_provider", _get_provider)

    builder = ab.OpenAIRegexBuilder()
    builder.build_pattern("show version", CONTEXT)
    builder.build_pattern("show clock", CONTEXT)

    assert calls == ["openai"]


def test_kwargs_override_max_tokens_and_pass_through_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeProvider(_ask_response())
    _patch_get_provider(monkeypatch, fake)

    builder = ab.OpenAIRegexBuilder()
    builder.build_pattern("show version", CONTEXT, max_tokens=2048, temperature=0.1)

    call = fake.calls[0]
    assert call["max_tokens"] == 2048
    assert call["temperature"] == 0.1


def test_api_key_construction_kwarg_reaches_get_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def _get_provider(provider, **kw):
        captured.update(provider=provider, **kw)
        return _FakeProvider(_ask_response())

    monkeypatch.setattr(ab.anyask, "get_provider", _get_provider)

    ab.OpenAIRegexBuilder(api_key="sk-test-123").build_pattern("show version", CONTEXT)

    assert captured == {"provider": "openai", "api_key": "sk-test-123"}


def test_vertexai_location_kwarg_renamed_to_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def _get_provider(provider, **kw):
        captured.update(provider=provider, **kw)
        return _FakeProvider(_ask_response())

    monkeypatch.setattr(ab.anyask, "get_provider", _get_provider)

    ab.VertexAIRegexBuilder(project="p", location="us-central1").build_pattern(
        "show version", CONTEXT
    )

    assert captured == {"provider": "vertexai", "project": "p", "region": "us-central1"}


def test_bedrock_and_oci_region_kwarg_not_renamed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def _get_provider(provider, **kw):
        captured.update(provider=provider, **kw)
        return _FakeProvider(_ask_response())

    monkeypatch.setattr(ab.anyask, "get_provider", _get_provider)

    ab.BedrockRegexBuilder(region="us-east-1").build_pattern("show version", CONTEXT)
    assert captured == {"provider": "bedrock", "region": "us-east-1"}

    captured.clear()
    ab.OCIRegexBuilder(compartment_id="ocid1...", region="us-ashburn-1").build_pattern(
        "show version", CONTEXT
    )
    assert captured == {
        "provider": "oci",
        "compartment_id": "ocid1...",
        "region": "us-ashburn-1",
    }


def test_azure_deployment_is_construction_kwarg_and_model_not_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    construction_captured = {}
    call_captured = {}

    def _get_provider(provider, **kw):
        construction_captured.update(provider=provider, **kw)
        fake = _FakeProvider(_ask_response())
        original = fake.generate_sync

        def _wrapped(prompt, **call_kw):
            call_captured.update(call_kw)
            return original(prompt, **call_kw)

        fake.generate_sync = _wrapped
        return fake

    monkeypatch.setattr(ab.anyask, "get_provider", _get_provider)

    builder = ab.AzureRegexBuilder(
        deployment="my-deployment",
        api_key="k",
        endpoint="https://foo",
        api_version="v1",
    )
    builder.build_pattern("show version", CONTEXT)

    assert construction_captured == {
        "provider": "azure",
        "deployment": "my-deployment",
        "api_key": "k",
        "endpoint": "https://foo",
        "api_version": "v1",
    }
    assert call_captured["model"] is None


def test_deepseek_disables_thinking_mode_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeProvider(_ask_response())
    _patch_get_provider(monkeypatch, fake)

    ab.DeepSeekRegexBuilder().build_pattern("show version", CONTEXT)

    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_deepseek_thinking_mode_override_is_respected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeProvider(_ask_response())
    _patch_get_provider(monkeypatch, fake)

    ab.DeepSeekRegexBuilder().build_pattern(
        "show version", CONTEXT, extra_body={"thinking": {"type": "enabled"}}
    )

    assert fake.calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}


_EXPECTED_PROVIDER_NAMES = {
    "AnthropicRegexBuilder": "anthropic",
    "AzureRegexBuilder": "azure",
    "BedrockRegexBuilder": "bedrock",
    "CerebrasRegexBuilder": "cerebras",
    "CohereRegexBuilder": "cohere",
    "DeepSeekRegexBuilder": "deepseek",
    "FireworksRegexBuilder": "fireworks",
    "GeminiRegexBuilder": "gemini",
    "GroqRegexBuilder": "groq",
    "MistralRegexBuilder": "mistral",
    "MoonshotRegexBuilder": "moonshot",
    "OCIRegexBuilder": "oci",
    "OpenAIRegexBuilder": "openai",
    "OpenRouterRegexBuilder": "openrouter",
    "PerplexityRegexBuilder": "perplexity",
    "TogetherRegexBuilder": "together",
    "VertexAIRegexBuilder": "vertexai",
    "XAIRegexBuilder": "xai",
}


@pytest.mark.parametrize(
    "class_name, provider", sorted(_EXPECTED_PROVIDER_NAMES.items())
)
def test_provider_attribute_matches_registered_name(
    class_name: str, provider: str
) -> None:
    cls = getattr(ab, class_name)
    assert cls.provider == provider
    assert issubclass(cls, ab.AnyAskRegexBuilder)
