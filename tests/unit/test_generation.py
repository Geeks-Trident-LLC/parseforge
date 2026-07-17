from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from parseforge.generation import GenerationResult, generate


@dataclass
class _FakeDeliveryOutput:
    output: str
    passed: bool
    error: str = ""


def _debug_json(
    *,
    api_key: str = "sk-real-secret-123",
    template: str = "raw llm template",
    canonical: str = "canonical template",
    readable: str = "readable dsl",
    recognizers: list | None = None,
    records: list | None = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
    total_tokens: int = 15,
    estimated_cost: float = 0.0042,
    duration_ms: float = 123.0,
) -> str:
    return json.dumps(
        {
            "llm_info": {
                "provider_name": "anthropic",
                "model": "claude-haiku-4-5-20251001",
                "api_key": api_key,
                "endpoint": "",
            },
            "llm_response": {"raw": {"id": "resp-1"}, "duration_ms": 100},
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": estimated_cost,
            },
            "generation_pipeline": {
                "model": "claude-haiku-4-5-20251001",
                "last_stage": {
                    "template": template,
                    "records": records or [],
                    "metadata": {
                        "template": template,
                        "records": records or [],
                        "variables": {},
                        "handling": [],
                        "response": {"raw": {"api_key": api_key}},
                    },
                    "ready": True,
                },
                "ready": True,
            },
            "dsl_pipeline": {
                "dsl": {
                    "raw_template": template,
                    "records": records or [],
                    "canonical": canonical,
                    "readable": readable,
                    "recognizers": recognizers or [],
                    "ready": True,
                },
                "ready": True,
            },
            "version": {"python_version": "3.12.0"},
            "status": {"state": "delivery", "errors": [], "passed": True},
            "duration_ms": duration_ms,
        }
    )


def test_generate_parses_successful_debug_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def _fake_run_pipeline(sample, provider, api_key, model, **kwargs):
        calls.append((sample, provider, api_key, model, kwargs))
        return _FakeDeliveryOutput(
            output=_debug_json(
                template="raw",
                canonical="canonical!",
                readable="readable!",
                recognizers=["r1", "r2"],
                records=[{"a": "1"}],
            ),
            passed=True,
        )

    monkeypatch.setattr("parseforge.generation.run_pipeline", _fake_run_pipeline)

    result = generate("sample text", "anthropic", "sk-real-secret-123", "some-model")

    assert isinstance(result, GenerationResult)
    assert result.template == "canonical!"
    assert result.raw_template == "raw"
    assert result.readable_dsl == "readable!"
    assert result.recognizers == ["r1", "r2"]
    assert result.records == [{"a": "1"}]
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.total_tokens == 15
    assert result.usage.estimated_cost == 0.0042
    assert result.duration_ms == 123.0
    assert result.ready is True
    assert result.reason == ""

    # mode/as_json are always forced, regardless of caller intent
    assert len(calls) == 1
    _, _, _, _, kwargs = calls[0]
    assert kwargs["mode"] == "debug"
    assert kwargs["as_json"] is True


def test_generate_redacts_api_key_everywhere_in_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "parseforge.generation.run_pipeline",
        lambda *a, **k: _FakeDeliveryOutput(
            output=_debug_json(api_key="sk-super-secret-do-not-leak"), passed=True
        ),
    )

    result = generate("sample text", "anthropic", "sk-super-secret-do-not-leak", "m")

    assert "sk-super-secret-do-not-leak" not in json.dumps(result.raw)
    assert result.raw["llm_info"]["api_key"] == "<redacted>"
    assert (
        result.raw["generation_pipeline"]["last_stage"]["metadata"]["response"]["raw"][
            "api_key"
        ]
        == "<redacted>"
    )


def test_generate_failure_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "parseforge.generation.run_pipeline",
        lambda *a, **k: _FakeDeliveryOutput(
            output=_debug_json(), passed=False, error="LLM call failed: rate limited"
        ),
    )

    result = generate("sample text", "anthropic", "sk-real-secret-123", "m")

    assert result.ready is False
    assert result.reason == "LLM call failed: rate limited"


def test_generate_forwards_extra_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def _fake_run_pipeline(sample, provider, api_key, model, **kwargs):
        calls.append(kwargs)
        return _FakeDeliveryOutput(output=_debug_json(), passed=True)

    monkeypatch.setattr("parseforge.generation.run_pipeline", _fake_run_pipeline)

    generate(
        "sample text",
        "azure",
        "sk-real-secret-123",
        "m",
        endpoint="https://example.com",
        max_tries=3,
    )

    assert calls[0]["endpoint"] == "https://example.com"
    assert calls[0]["max_tries"] == 3
