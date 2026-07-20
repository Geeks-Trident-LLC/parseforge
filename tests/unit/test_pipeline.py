from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from parseforge.generation import GenerationResult
from parseforge.generation import TokenUsage as GenerationTokenUsage
from parseforge.naming.llm import CliContext, LLMCLIResponse
from parseforge.naming.llm import TokenUsage as NamingTokenUsage
from parseforge.pipeline import LLMProviderConfig, TrialMetadata, run_command_pipeline
from parseforge.sampling import DeviceConnection

CONTEXT = CliContext(
    vendor="cisco", family="catalyst9200", os="ios-xe", version="17.9.1"
)
CONNECTION = DeviceConnection(
    host="10.0.0.1", username="admin", password="secret", device_type="cisco_ios"
)
GENERATION_CONFIG = LLMProviderConfig(
    provider="anthropic", api_key="sk-test", model="claude-haiku-4-5-20251001"
)

# A trivial but real TextFSM template: matches any single non-empty line.
_WORKING_TEMPLATE = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"
_BROKEN_TEMPLATE = "this is not a valid textfsm template !!!"


class FakeRegexBuilder:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.calls = 0

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        self.calls += 1
        return LLMCLIResponse(
            content=self.pattern,
            raw=None,
            usage=NamingTokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            duration_ms=1.0,
            reason="stop",
            ready=True,
        )


class FakeSampler:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[DeviceConnection, str]] = []

    def run_command(self, connection: DeviceConnection, command: str) -> str:
        self.calls.append((connection, command))
        return self.output


def _fake_generation_result(
    *, template: str = _WORKING_TEMPLATE, ready: bool = True
) -> GenerationResult:
    return GenerationResult(
        template=template,
        raw_template="raw " + template,
        readable_dsl="readable dsl text",
        recognizers=["r1", "r2"],
        records=[{"LINE": "hello world"}],
        usage=GenerationTokenUsage(
            input_tokens=20, output_tokens=8, total_tokens=28, estimated_cost=0.001
        ),
        duration_ms=456.0,
        ready=ready,
        reason="",
        raw={"status": {"passed": ready}},
    )


def test_run_command_pipeline_writes_expected_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "parseforge.generation.generate", lambda *a, **k: _fake_generation_result()
    )
    naming_builder = FakeRegexBuilder(r"show\s+clock")
    sampler = FakeSampler("hello world")

    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        naming_builder,
        sampler,
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )

    assert result.cli_name == "show-clock"
    assert result.passed is True
    assert result.duration_ms > 0
    assert isinstance(result.duration_ms, int)

    expected_run_dir = (
        tmp_path / "trials" / "cisco" / "catalyst9200" / "ios-xe" / "show-clock"
    )
    assert result.run_dir.parent == expected_run_dir

    samples_dir = result.run_dir / "samples"
    derive_dir = result.run_dir / "derive"

    assert (samples_dir / "sample.txt").read_text(encoding="utf-8") == "hello world"
    assert (derive_dir / "template.textfsm").read_text(
        encoding="utf-8"
    ) == _WORKING_TEMPLATE
    assert (derive_dir / "llm-template.textfsm").read_text(
        encoding="utf-8"
    ) == "raw " + _WORKING_TEMPLATE
    assert (derive_dir / "readable-dsl.txt").read_text(
        encoding="utf-8"
    ) == "readable dsl text"
    assert (derive_dir / "recognizers.txt").read_text(encoding="utf-8") == "r1\nr2"
    assert (result.run_dir / "summary.json").exists()


def test_sample_for_prompt_includes_reference_annotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "parseforge.generation.generate", lambda *a, **k: _fake_generation_result()
    )
    naming_builder = FakeRegexBuilder(r"show\s+clock")
    sampler = FakeSampler("hello world")

    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        naming_builder,
        sampler,
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )

    sample_for_prompt = (
        result.run_dir / "samples" / "sample-for-prompt.txt"
    ).read_text(encoding="utf-8")
    assert sample_for_prompt.startswith("hello world")
    assert "SAMPLE REFERENCE SOURCE" in sample_for_prompt
    assert 'a real "show clock" output from a cisco catalyst9200 ios-xe device' in (
        sample_for_prompt
    )


def test_generation_receives_sample_for_prompt_not_raw_sample(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = {}

    def _fake_generate(sample, provider, api_key, model, **kwargs):
        captured["sample"] = sample
        captured["provider"] = provider
        captured["api_key"] = api_key
        captured["model"] = model
        return _fake_generation_result()

    monkeypatch.setattr("parseforge.generation.generate", _fake_generate)

    run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        FakeRegexBuilder(r"show\s+clock"),
        FakeSampler("hello world"),
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )

    assert "SAMPLE REFERENCE SOURCE" in captured["sample"]
    assert captured["provider"] == "anthropic"
    assert captured["api_key"] == "sk-test"
    assert captured["model"] == "claude-haiku-4-5-20251001"


def test_naming_cache_hit_has_no_naming_usage_in_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "parseforge.generation.generate", lambda *a, **k: _fake_generation_result()
    )
    naming_builder = FakeRegexBuilder(r"show\s+clock")
    sampler = FakeSampler("hello world")

    # First run: cache miss, naming LLM called once.
    run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        naming_builder,
        sampler,
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )
    assert naming_builder.calls == 1

    # Second run: cache hit, naming LLM not called again.
    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        naming_builder,
        sampler,
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )
    assert naming_builder.calls == 1

    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["usage"]["naming"] is None
    assert summary["usage"]["generation"]["total_tokens"] == 28


def test_summary_json_shape(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "parseforge.generation.generate", lambda *a, **k: _fake_generation_result()
    )
    naming_builder = FakeRegexBuilder(r"show\s+clock")

    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        naming_builder,
        FakeSampler("hello world"),
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
        metadata=TrialMetadata(
            project="acme",
            username="tuyen",
            email="tuyen@example.com",
            description="desc",
        ),
    )

    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))

    assert summary["passed"] is True
    assert summary["error"] is None
    assert "mode" not in summary
    assert summary["metadata"] == {
        "project": "acme",
        "username": "tuyen",
        "email": "tuyen@example.com",
        "description": "desc",
    }
    assert summary["command_info"] == {
        "vendor": "cisco",
        "family": "catalyst9200",
        "os": "ios-xe",
        "version": "17.9.1",
        "device_type": "cisco_ios",
        "command": "show clock",
    }
    assert summary["usage"]["naming"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert summary["usage"]["generation"] == {
        "input_tokens": 20,
        "output_tokens": 8,
        "total_tokens": 28,
        "estimated_cost": 0.001,
    }
    assert summary["provider_info"] == {
        "provider": "anthropic",
        "model": "claude-haiku-4-5-20251001",
    }
    assert "created_at" in summary
    assert "ended_at" in summary
    assert summary["duration_ms"] > 0
    assert isinstance(summary["duration_ms"], int)


def test_passed_is_false_when_generation_not_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "parseforge.generation.generate",
        lambda *a, **k: _fake_generation_result(ready=False),
    )

    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        FakeRegexBuilder(r"show\s+clock"),
        FakeSampler("hello world"),
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )

    assert result.passed is False
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["error"] == "generation not ready"


def test_passed_is_false_when_template_does_not_parse_sample(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "parseforge.generation.generate",
        lambda *a, **k: _fake_generation_result(template=_BROKEN_TEMPLATE, ready=True),
    )

    result = run_command_pipeline(
        "show clock",
        CONTEXT,
        CONNECTION,
        FakeRegexBuilder(r"show\s+clock"),
        FakeSampler("hello world"),
        GENERATION_CONFIG,
        store_root=tmp_path,
        naming_index_path=tmp_path / ".cli-name.json",
    )

    assert result.passed is False
    summary = json.loads((result.run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["error"]
