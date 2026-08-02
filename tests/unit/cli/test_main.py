from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from click.testing import CliRunner

from parseforge.cli import config as cli_config
from parseforge.cli import main as cli_main
from parseforge.generation import GenerationResult
from parseforge.generation import TokenUsage as GenerationTokenUsage
from parseforge.integration import ReferenceGroup, ReferenceVariant
from parseforge.naming.llm import CliContext, LLMCLIResponse
from parseforge.naming.llm import TokenUsage as NamingTokenUsage
from parseforge.paths import DeviceKey
from parseforge.pipeline import TrialResult
from parseforge.promotion import (
    GroupEvaluation,
    PromotionDecision,
    PromotionMetadata,
    PromotionRunResult,
)
from parseforge.sampling import DeviceConnection

_WORKING_TEMPLATE = "Value LINE (.+)\n\nStart\n  ^${LINE} -> Record\n"

KEY = DeviceKey(
    vendor="cisco", family="catalyst9200", os="ios-xe", cli_name="show-clock"
)


class FakeRegexBuilder:
    def __init__(
        self, ready: bool = True, reason: str = "stop", content: str = "pattern"
    ) -> None:
        self.ready = ready
        self.reason = reason
        self.content = content
        self.calls: list[tuple[str, CliContext]] = []

    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        self.calls.append((command, context))
        return LLMCLIResponse(
            content=self.content,
            raw=None,
            usage=NamingTokenUsage(
                input_tokens=1, output_tokens=1, total_tokens=2, estimated_cost=0.0
            ),
            duration_ms=1.0,
            reason=self.reason,
            ready=self.ready,
        )


class FailingRegexBuilder:
    def build_pattern(
        self, command: str, context: CliContext, **kwargs: Any
    ) -> LLMCLIResponse:
        raise RuntimeError("boom")


class FakeSampler:
    def __init__(
        self, output: str | None = None, error: Exception | None = None
    ) -> None:
        self.output = output
        self.error = error
        self.calls: list[tuple[DeviceConnection, str]] = []

    def run_command(self, connection: DeviceConnection, command: str) -> str:
        self.calls.append((connection, command))
        if self.error is not None:
            raise self.error
        return self.output or ""


def _fake_generation_result(ready: bool = True, reason: str = "") -> GenerationResult:
    return GenerationResult(
        template=_WORKING_TEMPLATE,
        raw_template="raw",
        readable_dsl="readable description",
        recognizers=["r1", "r2"],
        records=[{"LINE": "hello"}],
        usage=GenerationTokenUsage(
            input_tokens=1, output_tokens=1, total_tokens=2, estimated_cost=0.0
        ),
        duration_ms=1.0,
        ready=ready,
        reason=reason,
        raw={},
    )


# --------------------------------------------------------------------------
# name
# --------------------------------------------------------------------------


def test_name_azure_forwards_endpoint_api_version_deployment(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _fake_builder(
        provider: str,
        api_key: str | None,
        model: str | None,
        endpoint: str | None = None,
        api_version: str | None = None,
        deployment: str | None = None,
    ) -> FakeRegexBuilder:
        captured.update(
            provider=provider,
            endpoint=endpoint,
            api_version=api_version,
            deployment=deployment,
        )
        # naming.cli_name() self-validates that the returned pattern
        # matches its own source command — "show version" is a fixed
        # string with no regex metacharacters, so it works as its own
        # matching pattern here.
        return FakeRegexBuilder(ready=True, content="show version")

    monkeypatch.setattr(cli_main, "_build_regex_builder", _fake_builder)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "name",
            "--vendor",
            "cisco",
            "--family",
            "catalyst9200",
            "--os",
            "ios-xe",
            "--version",
            "17.9.1",
            "--provider",
            "azure",
            "--api-key",
            "sk-test",
            "--endpoint",
            "https://my-resource.openai.azure.com",
            "--api-version",
            "2024-06-01",
            "--deployment",
            "my-deployment",
            "show",
            "version",
        ],
    )
    assert result.exit_code == 0
    assert captured["provider"] == "azure"
    assert captured["endpoint"] == "https://my-resource.openai.azure.com"
    assert captured["api_version"] == "2024-06-01"
    assert captured["deployment"] == "my-deployment"


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def test_run_azure_generation_config_uses_deployment_and_endpoint(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli_main, "_build_regex_builder", lambda *a, **k: FakeRegexBuilder()
    )
    captured: dict[str, Any] = {}

    def _fake_pipeline(
        command: str,
        context: CliContext,
        connection: DeviceConnection,
        naming_builder: Any,
        sampler: Any,
        generation_config: Any,
        **kwargs: Any,
    ) -> TrialResult:
        captured["generation_config"] = generation_config
        return TrialResult(
            run_dir=tmp_path, cli_name="show-clock", passed=True, duration_ms=1
        )

    monkeypatch.setattr(cli_main.pipeline, "run_command_pipeline", _fake_pipeline)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "run",
            "--vendor",
            "cisco",
            "--family",
            "catalyst9200",
            "--os",
            "ios-xe",
            "--version",
            "17.9.1",
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "secret",
            "--device-type",
            "cisco_ios",
            "--provider",
            "azure",
            "--api-key",
            "sk-test",
            "--model",
            "ignored-since-deployment-is-set",
            "--endpoint",
            "https://my-resource.openai.azure.com",
            "--api-version",
            "2024-06-01",
            "--deployment",
            "my-deployment",
            "show",
            "clock",
        ],
    )
    assert result.exit_code == 0
    gen_cfg = captured["generation_config"]
    assert gen_cfg.provider == "azure"
    assert gen_cfg.model == "my-deployment"
    assert gen_cfg.endpoint == "https://my-resource.openai.azure.com"
    assert gen_cfg.api_version == "2024-06-01"


# --------------------------------------------------------------------------
# check
# --------------------------------------------------------------------------


def test_check_requires_exactly_one_of_connector_or_provider() -> None:
    result = CliRunner().invoke(cli_main.main, ["check"])
    assert result.exit_code != 0
    assert "specify exactly one" in result.output

    result = CliRunner().invoke(
        cli_main.main, ["check", "--connector", "netmiko", "--provider", "anthropic"]
    )
    assert result.exit_code != 0
    assert "specify exactly one" in result.output


def test_check_connector_with_nothing_given_prints_guidance() -> None:
    result = CliRunner().invoke(cli_main.main, ["check", "--connector", "netmiko"])
    assert result.exit_code == 0
    assert "needs: --host" in result.output


def test_check_connector_ok(monkeypatch: Any) -> None:
    monkeypatch.setattr(cli_main, "_build_sampler", lambda connector: FakeSampler("ok"))
    result = CliRunner().invoke(
        cli_main.main,
        [
            "check",
            "--connector",
            "netmiko",
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "secret",
            "--device-type",
            "cisco_ios",
        ],
    )
    assert result.exit_code == 0
    assert "OK" in result.output


def test_check_connector_fail(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        cli_main,
        "_build_sampler",
        lambda connector: FakeSampler(error=RuntimeError("no route")),
    )
    result = CliRunner().invoke(
        cli_main.main,
        [
            "check",
            "--connector",
            "netmiko",
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "secret",
            "--device-type",
            "cisco_ios",
        ],
    )
    assert result.exit_code == 1
    assert "FAIL: no route" in result.output


def test_check_connector_env_missing_vars(monkeypatch: Any) -> None:
    monkeypatch.delenv("WIDGET_SANDBOX_HOST", raising=False)
    result = CliRunner().invoke(
        cli_main.main, ["check", "--connector", "netmiko", "--env", "widget"]
    )
    assert result.exit_code != 0
    assert "WIDGET_SANDBOX_HOST" in result.output


def test_check_connector_env_resolves(monkeypatch: Any) -> None:
    monkeypatch.setenv("WIDGET_SANDBOX_HOST", "10.0.0.9")
    monkeypatch.setenv("WIDGET_SANDBOX_USERNAME", "admin")
    monkeypatch.setenv("WIDGET_SANDBOX_PASSWORD", "secret")
    monkeypatch.setenv("WIDGET_SANDBOX_DEVICE_TYPE", "cisco_ios")
    monkeypatch.setattr(cli_main, "_build_sampler", lambda connector: FakeSampler("ok"))
    result = CliRunner().invoke(
        cli_main.main, ["check", "--connector", "netmiko", "--env", "widget"]
    )
    assert result.exit_code == 0
    assert "OK" in result.output


def test_check_provider_ok(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        cli_main,
        "_build_regex_builder",
        lambda p, k, m, *a: FakeRegexBuilder(ready=True),
    )
    result = CliRunner().invoke(cli_main.main, ["check", "--provider", "anthropic"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_check_provider_not_ready(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        cli_main,
        "_build_regex_builder",
        lambda p, k, m, *a: FakeRegexBuilder(ready=False, reason="max_tokens"),
    )
    result = CliRunner().invoke(cli_main.main, ["check", "--provider", "anthropic"])
    assert result.exit_code == 1
    assert "FAIL: max_tokens" in result.output


def test_check_provider_raises(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        cli_main, "_build_regex_builder", lambda p, k, m, *a: FailingRegexBuilder()
    )
    result = CliRunner().invoke(cli_main.main, ["check", "--provider", "anthropic"])
    assert result.exit_code == 1
    assert "FAIL: boom" in result.output


def test_check_provider_azure_forwards_endpoint_api_version_deployment(
    monkeypatch: Any,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_builder(
        provider: str,
        api_key: str | None,
        model: str | None,
        endpoint: str | None = None,
        api_version: str | None = None,
        deployment: str | None = None,
    ) -> FakeRegexBuilder:
        captured.update(
            endpoint=endpoint, api_version=api_version, deployment=deployment
        )
        return FakeRegexBuilder(ready=True)

    monkeypatch.setattr(cli_main, "_build_regex_builder", _fake_builder)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "check",
            "--provider",
            "azure",
            "--endpoint",
            "https://my-resource.openai.azure.com",
            "--api-version",
            "2024-06-01",
            "--deployment",
            "my-deployment",
        ],
    )
    assert result.exit_code == 0
    assert "OK" in result.output
    assert captured["endpoint"] == "https://my-resource.openai.azure.com"
    assert captured["api_version"] == "2024-06-01"
    assert captured["deployment"] == "my-deployment"


# --------------------------------------------------------------------------
# generate-template
# --------------------------------------------------------------------------


def test_generate_template_requires_an_input_mode() -> None:
    result = CliRunner().invoke(
        cli_main.main,
        [
            "generate-template",
            "--provider",
            "anthropic",
            "--api-key",
            "sk-test",
            "--model",
            "claude-haiku-4-5-20251001",
        ],
    )
    assert result.exit_code != 0
    assert "specify --sample-file" in result.output


def test_generate_template_requires_provider_key_model(tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    result = CliRunner().invoke(
        cli_main.main, ["generate-template", "--sample-file", str(sample_path)]
    )
    assert result.exit_code != 0
    assert "--provider, --api-key, and --model" in result.output


def test_generate_template_from_sample_file(monkeypatch: Any, tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(
        cli_main.generation, "generate", lambda *a, **k: _fake_generation_result()
    )

    result = CliRunner().invoke(
        cli_main.main,
        [
            "generate-template",
            "--sample-file",
            str(sample_path),
            "--provider",
            "anthropic",
            "--api-key",
            "sk-test",
            "--model",
            "claude-haiku-4-5-20251001",
        ],
    )
    assert result.exit_code == 0
    assert "readable description" in result.output
    assert "r1" in result.output


def test_generate_template_not_ready_raises(monkeypatch: Any, tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(
        cli_main.generation,
        "generate",
        lambda *a, **k: _fake_generation_result(ready=False, reason="truncated"),
    )

    result = CliRunner().invoke(
        cli_main.main,
        [
            "generate-template",
            "--sample-file",
            str(sample_path),
            "--provider",
            "anthropic",
            "--api-key",
            "sk-test",
            "--model",
            "claude-haiku-4-5-20251001",
        ],
    )
    assert result.exit_code != 0
    assert "truncated" in result.output


def test_generate_template_writes_out_dir(monkeypatch: Any, tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    out_dir = tmp_path / "out"
    monkeypatch.setattr(
        cli_main.generation, "generate", lambda *a, **k: _fake_generation_result()
    )

    result = CliRunner().invoke(
        cli_main.main,
        [
            "generate-template",
            "--sample-file",
            str(sample_path),
            "--provider",
            "anthropic",
            "--api-key",
            "sk-test",
            "--model",
            "claude-haiku-4-5-20251001",
            "--out",
            str(out_dir),
        ],
    )
    assert result.exit_code == 0
    assert (out_dir / "template.textfsm").read_text(
        encoding="utf-8"
    ) == _WORKING_TEMPLATE
    assert (out_dir / "readable-dsl.txt").exists()
    assert (out_dir / "recognizers.txt").read_text(encoding="utf-8") == "r1\nr2"


def test_generate_template_from_config(monkeypatch: Any, tmp_path: Path) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    config_path = tmp_path / "gen.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "provider": "anthropic",
                "api_key": "sk-test",
                "model": "claude-haiku-4-5-20251001",
                "sample_file": str(sample_path),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli_main.generation, "generate", lambda *a, **k: _fake_generation_result()
    )

    result = CliRunner().invoke(
        cli_main.main, ["generate-template", "--config", str(config_path)]
    )
    assert result.exit_code == 0
    assert "readable description" in result.output


def test_generate_template_azure_uses_deployment_and_endpoint(
    monkeypatch: Any, tmp_path: Path
) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    def _fake_generate(
        sample: str, provider: str, api_key: str, model: str, **kwargs: Any
    ) -> GenerationResult:
        captured.update(provider=provider, model=model, **kwargs)
        return _fake_generation_result()

    monkeypatch.setattr(cli_main.generation, "generate", _fake_generate)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "generate-template",
            "--sample-file",
            str(sample_path),
            "--provider",
            "azure",
            "--api-key",
            "sk-test",
            "--model",
            "ignored-since-deployment-is-set",
            "--endpoint",
            "https://my-resource.openai.azure.com",
            "--api-version",
            "2024-06-01",
            "--deployment",
            "my-deployment",
        ],
    )
    assert result.exit_code == 0
    assert captured["model"] == "my-deployment"
    assert captured["endpoint"] == "https://my-resource.openai.azure.com"
    assert captured["api_version"] == "2024-06-01"


def test_generate_template_azure_api_version_defaults_when_unset(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.delenv("AZURE_API_VERSION", raising=False)
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    captured: dict[str, Any] = {}

    def _fake_generate(
        sample: str, provider: str, api_key: str, model: str, **kwargs: Any
    ) -> GenerationResult:
        captured.update(**kwargs)
        return _fake_generation_result()

    monkeypatch.setattr(cli_main.generation, "generate", _fake_generate)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "generate-template",
            "--sample-file",
            str(sample_path),
            "--provider",
            "azure",
            "--api-key",
            "sk-test",
            "--model",
            "ignored",
            "--endpoint",
            "https://my-resource.openai.azure.com",
            "--deployment",
            "my-deployment",
        ],
    )
    assert result.exit_code == 0
    assert captured["api_version"] == cli_main.DEFAULT_API_VERSION


def test_generate_template_from_config_azure_fields(
    monkeypatch: Any, tmp_path: Path
) -> None:
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello\n", encoding="utf-8")
    config_path = tmp_path / "gen.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "provider": "azure",
                "api_key": "sk-test",
                "model": "ignored-since-deployment-is-set",
                "sample_file": str(sample_path),
                "endpoint": "https://my-resource.openai.azure.com",
                "api_version": "2024-06-01",
                "deployment": "my-deployment",
            }
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def _fake_generate(
        sample: str, provider: str, api_key: str, model: str, **kwargs: Any
    ) -> GenerationResult:
        captured.update(model=model, **kwargs)
        return _fake_generation_result()

    monkeypatch.setattr(cli_main.generation, "generate", _fake_generate)

    result = CliRunner().invoke(
        cli_main.main, ["generate-template", "--config", str(config_path)]
    )
    assert result.exit_code == 0
    assert captured["model"] == "my-deployment"
    assert captured["endpoint"] == "https://my-resource.openai.azure.com"
    assert captured["api_version"] == "2024-06-01"


# --------------------------------------------------------------------------
# init-generate-template-config
# --------------------------------------------------------------------------


def test_init_generate_template_config_writes_placeholder(tmp_path: Path) -> None:
    out_path = tmp_path / "generate-template.yaml"
    result = CliRunner().invoke(
        cli_main.main, ["init-generate-template-config", "--out", str(out_path)]
    )
    assert result.exit_code == 0
    assert f"wrote {out_path}" in result.output

    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert data["provider"] == "anthropic"
    assert data["api_key"] == "<api-key>"
    assert data["model"] == "<model>"
    assert data["sample_file"] == "<path/to/sample.txt>"
    assert "connector" not in data


def test_init_generate_template_config_refuses_to_overwrite(tmp_path: Path) -> None:
    out_path = tmp_path / "generate-template.yaml"
    out_path.write_text("existing content\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_main.main, ["init-generate-template-config", "--out", str(out_path)]
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert out_path.read_text(encoding="utf-8") == "existing content\n"


def test_init_generate_template_config_force_overwrites(tmp_path: Path) -> None:
    out_path = tmp_path / "generate-template.yaml"
    out_path.write_text("existing content\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_main.main,
        ["init-generate-template-config", "--out", str(out_path), "--force"],
    )

    assert result.exit_code == 0
    assert "provider:" in out_path.read_text(encoding="utf-8")


def test_init_generate_template_config_loads_via_config_loader(
    tmp_path: Path,
) -> None:
    """The generated placeholder is valid YAML with every required key
    present -- load_generation_config should accept it structurally."""
    out_path = tmp_path / "generate-template.yaml"
    CliRunner().invoke(
        cli_main.main, ["init-generate-template-config", "--out", str(out_path)]
    )

    cfg = cli_config.load_generation_config(out_path)

    assert cfg.provider == "anthropic"
    assert cfg.sample_file == "<path/to/sample.txt>"
    assert cfg.connector is None


# --------------------------------------------------------------------------
# canonical / readable / recognizers
# --------------------------------------------------------------------------


def test_canonical_requires_sample(tmp_path: Path) -> None:
    template_path = tmp_path / "template.textfsm"
    template_path.write_text(_WORKING_TEMPLATE, encoding="utf-8")
    result = CliRunner().invoke(cli_main.main, ["canonical", str(template_path)])
    assert result.exit_code != 0
    assert "--sample" in result.output


def test_canonical_with_sample(tmp_path: Path) -> None:
    template_path = tmp_path / "template.textfsm"
    template_path.write_text(_WORKING_TEMPLATE, encoding="utf-8")
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello world\n", encoding="utf-8")
    result = CliRunner().invoke(
        cli_main.main, ["canonical", str(template_path), "--sample", str(sample_path)]
    )
    assert result.exit_code == 0
    assert "Value LINE" in result.output


def test_readable_with_sample(tmp_path: Path) -> None:
    template_path = tmp_path / "template.textfsm"
    template_path.write_text(_WORKING_TEMPLATE, encoding="utf-8")
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello world\n", encoding="utf-8")
    result = CliRunner().invoke(
        cli_main.main, ["readable", str(template_path), "--sample", str(sample_path)]
    )
    assert result.exit_code == 0
    assert result.output.strip() != ""


def test_recognizers_prints_one_per_line(tmp_path: Path) -> None:
    template_path = tmp_path / "template.textfsm"
    template_path.write_text(_WORKING_TEMPLATE, encoding="utf-8")
    sample_path = tmp_path / "sample.txt"
    sample_path.write_text("hello world\n", encoding="utf-8")
    result = CliRunner().invoke(
        cli_main.main,
        ["recognizers", str(template_path), "--sample", str(sample_path)],
    )
    assert result.exit_code == 0


# --------------------------------------------------------------------------
# init-trial-config
# --------------------------------------------------------------------------


def test_init_trial_config_writes_placeholder(tmp_path: Path) -> None:
    out_path = tmp_path / "trial.yaml"
    result = CliRunner().invoke(
        cli_main.main, ["init-trial-config", "--out", str(out_path)]
    )
    assert result.exit_code == 0
    assert f"wrote {out_path}" in result.output

    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    for key in (
        "vendor",
        "family",
        "os",
        "version",
        "connector",
        "host",
        "username",
        "password",
        "device_type",
        "provider",
        "api_key",
        "model",
        "commands",
        "user",
    ):
        assert key in data
    assert data["commands"] == ["<show command>"]


def test_init_trial_config_refuses_to_overwrite(tmp_path: Path) -> None:
    out_path = tmp_path / "trial.yaml"
    out_path.write_text("existing content\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_main.main, ["init-trial-config", "--out", str(out_path)]
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert out_path.read_text(encoding="utf-8") == "existing content\n"


def test_init_trial_config_force_overwrites(tmp_path: Path) -> None:
    out_path = tmp_path / "trial.yaml"
    out_path.write_text("existing content\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_main.main, ["init-trial-config", "--out", str(out_path), "--force"]
    )

    assert result.exit_code == 0
    assert "vendor:" in out_path.read_text(encoding="utf-8")


def test_init_trial_config_placeholder_is_missing_required_values(
    tmp_path: Path,
) -> None:
    """The generated placeholder is valid YAML but every value still needs
    editing -- load_trial_config should accept it structurally (every
    required key is present and non-empty) without pretending the
    placeholder values are usable."""
    out_path = tmp_path / "trial.yaml"
    CliRunner().invoke(cli_main.main, ["init-trial-config", "--out", str(out_path)])

    cfg = cli_config.load_trial_config(out_path)

    assert cfg.host == "<device-host-or-ip>"
    assert cfg.provider == "anthropic"


# --------------------------------------------------------------------------
# trial
# --------------------------------------------------------------------------


def _write_trial_config(path: Path, store_root: Path, **overrides: Any) -> Path:
    config: dict[str, Any] = {
        "vendor": "cisco",
        "family": "catalyst9200",
        "os": "ios-xe",
        "version": "17.9.1",
        "connector": "netmiko",
        "host": "10.0.0.1",
        "username": "admin",
        "password": "secret",
        "device_type": "cisco_ios",
        "provider": "anthropic",
        "api_key": "sk-test",
        "model": "claude-haiku-4-5-20251001",
        "commands": ["show clock", "show version"],
        "user": "alice",
        "path": str(store_root),
    }
    config.update(overrides)
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_trial_missing_required_key_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "trial.yaml"
    config_path.write_text(yaml.safe_dump({"vendor": "cisco"}), encoding="utf-8")
    result = CliRunner().invoke(cli_main.main, ["trial", "--config", str(config_path)])
    assert result.exit_code != 0
    assert "missing required config key" in result.output


def test_trial_runs_every_command(monkeypatch: Any, tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    config_path = _write_trial_config(tmp_path / "trial.yaml", store_root)
    monkeypatch.setattr(cli_main, "_build_sampler", lambda connector: FakeSampler("ok"))

    calls: list[str] = []

    def _fake_pipeline(command: str, *args: Any, **kwargs: Any) -> TrialResult:
        calls.append(command)
        return TrialResult(
            run_dir=store_root / "trials" / command.replace(" ", "-"),
            cli_name=command.replace(" ", "-"),
            passed=True,
            duration_ms=1,
        )

    monkeypatch.setattr(cli_main.pipeline, "run_command_pipeline", _fake_pipeline)

    result = CliRunner().invoke(cli_main.main, ["trial", "--config", str(config_path)])
    assert result.exit_code == 0
    assert calls == ["show clock", "show version"]
    assert "2/2 passed" in result.output


def test_trial_path_flag_overrides_config(monkeypatch: Any, tmp_path: Path) -> None:
    config_store_root = tmp_path / "config-store"
    override_store_root = tmp_path / "override-store"
    config_path = _write_trial_config(tmp_path / "trial.yaml", config_store_root)
    monkeypatch.setattr(cli_main, "_build_sampler", lambda connector: FakeSampler("ok"))

    seen_store_roots: list[Path] = []

    def _fake_pipeline(command: str, *args: Any, **kwargs: Any) -> TrialResult:
        seen_store_roots.append(kwargs["store_root"])
        return TrialResult(run_dir=Path("x"), cli_name="x", passed=True, duration_ms=1)

    monkeypatch.setattr(cli_main.pipeline, "run_command_pipeline", _fake_pipeline)

    result = CliRunner().invoke(
        cli_main.main,
        ["trial", "--config", str(config_path), "--path", str(override_store_root)],
    )
    assert result.exit_code == 0
    assert all(root == override_store_root for root in seen_store_roots)


def test_trial_workers_runs_concurrently(monkeypatch: Any, tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    config_path = _write_trial_config(
        tmp_path / "trial.yaml",
        store_root,
        commands=["show clock", "show version", "show inventory"],
        workers=3,
    )
    monkeypatch.setattr(cli_main, "_build_sampler", lambda connector: FakeSampler("ok"))

    def _fake_pipeline(command: str, *args: Any, **kwargs: Any) -> TrialResult:
        return TrialResult(
            run_dir=Path("x"), cli_name=command, passed=True, duration_ms=1
        )

    monkeypatch.setattr(cli_main.pipeline, "run_command_pipeline", _fake_pipeline)

    result = CliRunner().invoke(cli_main.main, ["trial", "--config", str(config_path)])
    assert result.exit_code == 0
    assert "3/3 passed" in result.output


def test_trial_azure_generation_config_uses_deployment_and_endpoint(
    monkeypatch: Any, tmp_path: Path
) -> None:
    store_root = tmp_path / "store"
    config_path = _write_trial_config(
        tmp_path / "trial.yaml",
        store_root,
        provider="azure",
        model="ignored-since-deployment-is-set",
        endpoint="https://my-resource.openai.azure.com",
        api_version="2024-06-01",
        deployment="my-deployment",
    )
    monkeypatch.setattr(cli_main, "_build_sampler", lambda connector: FakeSampler("ok"))
    captured: dict[str, Any] = {}

    def _fake_pipeline(
        command: str,
        context: CliContext,
        connection: DeviceConnection,
        naming_builder: Any,
        sampler: Any,
        generation_config: Any,
        **kwargs: Any,
    ) -> TrialResult:
        captured["generation_config"] = generation_config
        return TrialResult(
            run_dir=store_root, cli_name=command, passed=True, duration_ms=1
        )

    monkeypatch.setattr(cli_main.pipeline, "run_command_pipeline", _fake_pipeline)

    result = CliRunner().invoke(cli_main.main, ["trial", "--config", str(config_path)])
    assert result.exit_code == 0
    gen_cfg = captured["generation_config"]
    assert gen_cfg.provider == "azure"
    assert gen_cfg.model == "my-deployment"
    assert gen_cfg.endpoint == "https://my-resource.openai.azure.com"
    assert gen_cfg.api_version == "2024-06-01"


# --------------------------------------------------------------------------
# integration
# --------------------------------------------------------------------------


def test_integration_no_trials(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(cli_main.paths, "discover_device_keys", lambda store_root: [])
    result = CliRunner().invoke(cli_main.main, ["integration", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "no trials found" in result.output


def test_integration_reports_groups_and_variants(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        cli_main.paths, "discover_device_keys", lambda store_root: [KEY]
    )
    reference = {
        "group1": ReferenceGroup(
            keys=["LINE"],
            sample_path="s.txt",
            variants={"1": ReferenceVariant("t.textfsm", 3, 3)},
        )
    }
    monkeypatch.setattr(
        cli_main.integration, "build_integration", lambda store_root, key: reference
    )
    summary_path = tmp_path / "integration" / "reference-summary.json"
    monkeypatch.setattr(
        cli_main.integration, "write_reference_summary", lambda store_root: summary_path
    )

    result = CliRunner().invoke(cli_main.main, ["integration", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert "1 group(s), 1 variant(s)" in result.output
    assert str(summary_path) in result.output


# --------------------------------------------------------------------------
# promotion
# --------------------------------------------------------------------------


def test_promotion_requires_user() -> None:
    result = CliRunner().invoke(cli_main.main, ["promotion"])
    assert result.exit_code != 0


def test_promotion_reports_promoted_and_unqualified(
    monkeypatch: Any, tmp_path: Path
) -> None:
    fake_result = PromotionRunResult(
        promoted=[tmp_path / "authoritative" / "template.textfsm"],
        unqualified=[
            GroupEvaluation(
                case_key="cisco/catalyst9200/ios-xe/show-clock",
                group_id="group2",
                decision=PromotionDecision.QUEUED_FOR_REVIEW,
                match_rate=0.5,
                sample_count=2,
            )
        ],
        unmatched_cases=[],
        invalid_requests=[],
    )

    captured: dict[str, Any] = {}

    def _fake_promote_auto(
        store_root: Path, metadata: PromotionMetadata, gate: Any
    ) -> PromotionRunResult:
        captured["metadata"] = metadata
        captured["gate"] = gate
        return fake_result

    monkeypatch.setattr(cli_main.promotion, "promote_auto", _fake_promote_auto)

    result = CliRunner().invoke(
        cli_main.main,
        [
            "promotion",
            "--user",
            "alice",
            "--path",
            str(tmp_path),
            "--threshold",
            "0.9",
            "--min-samples",
            "2",
        ],
    )
    assert result.exit_code == 0
    assert "promoted: " in result.output
    assert "unqualified: cisco/catalyst9200/ios-xe/show-clock group2" in result.output
    assert "1 promoted, 1 unqualified" in result.output
    assert captured["metadata"].user == "alice"
    assert captured["gate"].match_rate_threshold == 0.9
    assert captured["gate"].min_sample_count == 2
