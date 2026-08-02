"""parseforge CLI entry point."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import click
from textfsm_ai.api import DSLResult, compile_dsl

from parseforge import (
    generation,
    integration,
    naming,
    paths,
    pipeline,
    promotion,
    sampling,
    validation,
)
from parseforge.cli import config as cli_config

_BUILDERS: dict[str, type[naming.RegexBuilder]] = {
    "anthropic": naming.AnthropicRegexBuilder,
    "deepseek": naming.DeepSeekRegexBuilder,
    "fireworks": naming.FireworksRegexBuilder,
    "groq": naming.GroqRegexBuilder,
    "openai": naming.OpenAIRegexBuilder,
    "openrouter": naming.OpenRouterRegexBuilder,
    "perplexity": naming.PerplexityRegexBuilder,
    "together": naming.TogetherRegexBuilder,
    "xai": naming.XAIRegexBuilder,
}

_CONNECTORS = ("netmiko",)

_TRIAL_CONFIG_PLACEHOLDER = """\
# parseforge trial config -- see README.md's `trial` section for details.
# Replace every <...> placeholder below, then run:
#   parseforge trial --config trial.yaml

# --- device / command context (required) ---
vendor: <vendor>
family: <family>
os: <os>
version: <os-version>

# --- connector (required) ---
connector: netmiko
host: <device-host-or-ip>
username: <device-username>
password: <device-password>
device_type: <netmiko-device-type>

# --- LLM provider (required) -- shared for both naming and generation ---
provider: anthropic
api_key: <api-key>
model: <model>

# --- commands to run (required, at least one) ---
commands:
  - <show command>

# --- who ran this (required) ---
user: <your-name>

# --- optional ---
# email: you@example.com
# description: short description of this trial batch
# notes: any additional context
# workers: 1
# path: /path/to/store/root
"""

_GENERATE_TEMPLATE_CONFIG_PLACEHOLDER = """\
# parseforge generate-template config -- see README.md's `generate-template`
# section for details. Replace every <...> placeholder below, then run:
#   parseforge generate-template --config generate-template.yaml

# --- LLM provider (required) ---
provider: anthropic
api_key: <api-key>
model: <model>

# --- input: choose exactly one ---

# Option A: a sample already captured to a file
sample_file: <path/to/sample.txt>

# Option B: sample live from a device -- comment out sample_file above, then
# uncomment and fill in below (env can replace host/username/password/
# device_type, same convention as `check --env`)
# connector: netmiko
# cmdline: <show command>
# host: <device-host-or-ip>
# username: <device-username>
# password: <device-password>
# device_type: <netmiko-device-type>
# env: <sandbox-env-name>
"""


def _write_placeholder_config(out_path: str, force: bool, content: str) -> None:
    path = Path(out_path)
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists — pass --force to overwrite")
    path.write_text(content, encoding="utf-8")
    click.echo(f"wrote {path}")


def _build_regex_builder(
    provider: str, api_key: str | None, model: str | None
) -> naming.RegexBuilder:
    kwargs: dict[str, str] = {}
    if api_key is not None:
        kwargs["api_key"] = api_key
    if model is not None:
        kwargs["model"] = model
    return _BUILDERS[provider](**kwargs)


def _build_sampler(connector: str) -> sampling.Sampler:
    """Deferred import — netmiko is an optional extra (parseforge[sampling]);
    nothing else in this module should require it to be installed."""
    if connector == "netmiko":
        from parseforge.sampling.backends import NetmikoSampler

        return NetmikoSampler()
    raise click.UsageError(f"unknown connector: {connector!r}")


def _resolve_env_connection(env_name: str) -> sampling.DeviceConnection:
    """Reads {ENV_NAME}_SANDBOX_{HOST,USERNAME,PASSWORD,DEVICE_TYPE} — the same
    convention tests/conftest.py already uses for CISCO_SANDBOX_*, generalized
    to any name."""
    prefix = f"{env_name.upper()}_SANDBOX_"
    values: dict[str, str] = {}
    missing: list[str] = []
    for field in ("HOST", "USERNAME", "PASSWORD", "DEVICE_TYPE"):
        var = f"{prefix}{field}"
        value = os.environ.get(var)
        if not value:
            missing.append(var)
        else:
            values[field] = value
    if missing:
        raise click.ClickException(
            f"--env={env_name} is missing environment variable(s): {', '.join(missing)}"
        )
    return sampling.DeviceConnection(
        host=values["HOST"],
        username=values["USERNAME"],
        password=values["PASSWORD"],
        device_type=values["DEVICE_TYPE"],
    )


def _resolve_connection(
    env: str | None,
    host: str | None,
    username: str | None,
    password: str | None,
    device_type: str | None,
) -> sampling.DeviceConnection:
    if env:
        return _resolve_env_connection(env)
    if host and username and password and device_type:
        return sampling.DeviceConnection(
            host=host, username=username, password=password, device_type=device_type
        )
    raise click.UsageError(
        "specify --env=<name>, or --host/--username/--password/--device-type"
    )


def _compile_dsl(template_file: str, sample_file: str) -> DSLResult:
    """compile_dsl() needs at least one example record to build its AST —
    an empty records list fails with BUILD-AST-ERROR, so a sample isn't
    optional in practice."""
    template_text = Path(template_file).read_text(encoding="utf-8")
    sample_text = Path(sample_file).read_text(encoding="utf-8")
    records = validation.parse(template_text, sample_text).records
    return compile_dsl(template_text, records)


@click.group()
@click.version_option(package_name="parseforge")
def main() -> None:
    """ParseForge — forge, validate, and promote TextFSM templates from CLI output."""


@main.command("name")
@click.option("--vendor", required=True)
@click.option("--family", required=True)
@click.option("--os", "os_", required=True)
@click.option("--version", required=True)
@click.option(
    "--provider",
    type=click.Choice(sorted(_BUILDERS)),
    default="anthropic",
    show_default=True,
)
@click.option(
    "--api-key",
    default=None,
    help="Provider API key. Defaults to that provider's own API key environment "
    "variable (ANTHROPIC_API_KEY, OPENAI_API_KEY, DEEPSEEK_API_KEY, GROQ_API_KEY, "
    "XAI_API_KEY, TOGETHER_API_KEY, FIREWORKS_API_KEY, PERPLEXITY_API_KEY, "
    "OPENROUTER_API_KEY); only needed on a cache miss.",
)
@click.option(
    "--model",
    default=None,
    help="Defaults to the selected provider's own default model.",
)
@click.argument("command", nargs=-1, required=True)
def name_cmd(
    vendor: str,
    family: str,
    os_: str,
    version: str,
    provider: str,
    api_key: str | None,
    model: str | None,
    command: tuple[str, ...],
) -> None:
    """Print the canonical cli-name for a raw CLI COMMAND.

    Looked up in the local cache first; only sent to the selected --provider
    on a cache miss.
    """
    context = naming.CliContext(vendor=vendor, family=family, os=os_, version=version)
    builder = _build_regex_builder(provider, api_key, model)
    click.echo(naming.cli_name(" ".join(command), context, builder=builder))


@main.command("run")
@click.option("--vendor", required=True)
@click.option("--family", required=True)
@click.option("--os", "os_", required=True)
@click.option("--version", required=True)
@click.option("--host", required=True, help="Device host/IP to sample from.")
@click.option("--username", required=True)
@click.option(
    "--password",
    required=True,
    envvar="PARSEFORGE_DEVICE_PASSWORD",
    help="Device password. Defaults to the PARSEFORGE_DEVICE_PASSWORD "
    "environment variable.",
)
@click.option(
    "--device-type",
    required=True,
    help='Netmiko device_type, e.g. "cisco_ios".',
)
@click.option(
    "--naming-provider",
    type=click.Choice(sorted(_BUILDERS)),
    default="anthropic",
    show_default=True,
)
@click.option(
    "--naming-api-key",
    default=None,
    help="API key for the naming LLM call. Defaults to that provider's own "
    "API key environment variable; only needed on a cache miss.",
)
@click.option(
    "--naming-model",
    default=None,
    help="Defaults to the naming provider's own default model.",
)
@click.option(
    "--provider",
    required=True,
    help="LLM provider for template generation (textfsm-ai's own registry, "
    'e.g. "anthropic", "openai", "deepseek", "groq", "xai", "together", '
    '"fireworks", "perplexity", "openrouter"). Naming uses its own separate '
    "--naming-provider, not this one.",
)
@click.option("--api-key", required=True, help="API key for the generation LLM call.")
@click.option("--model", required=True, help="Model for the generation LLM call.")
@click.option(
    "--store-root",
    default=None,
    help="Root directory for trial output. Defaults to ~/.parseforge/tests.",
)
@click.option("--project", default=None)
@click.option("--email", default=None)
@click.option("--description", default=None)
@click.argument("command", nargs=-1, required=True)
def run_cmd(
    vendor: str,
    family: str,
    os_: str,
    version: str,
    host: str,
    username: str,
    password: str,
    device_type: str,
    naming_provider: str,
    naming_api_key: str | None,
    naming_model: str | None,
    provider: str,
    api_key: str,
    model: str,
    store_root: str | None,
    project: str | None,
    email: str | None,
    description: str | None,
    command: tuple[str, ...],
) -> None:
    """Run a single trial: sample COMMAND from a device, generate a
    TextFSM template for it, and write the result under a trial
    directory (SPEC.md §5 steps 1-7)."""
    from pathlib import Path

    from parseforge import paths
    from parseforge.pipeline import (
        LLMProviderConfig,
        TrialMetadata,
        run_command_pipeline,
    )
    from parseforge.sampling import DeviceConnection
    from parseforge.sampling.backends import NetmikoSampler

    context = naming.CliContext(vendor=vendor, family=family, os=os_, version=version)
    connection = DeviceConnection(
        host=host, username=username, password=password, device_type=device_type
    )
    naming_builder = _build_regex_builder(naming_provider, naming_api_key, naming_model)
    generation_config = LLMProviderConfig(
        provider=provider, api_key=api_key, model=model
    )
    metadata = TrialMetadata(
        project=project,
        username=username,
        email=email,
        description=description,
    )

    result = run_command_pipeline(
        " ".join(command),
        context,
        connection,
        naming_builder,
        NetmikoSampler(),
        generation_config,
        store_root=Path(store_root) if store_root else paths.DEFAULT_STORE_ROOT,
        metadata=metadata,
    )
    click.echo(f"cli_name : {result.cli_name}")
    click.echo(f"passed   : {result.passed}")
    click.echo(f"run_dir  : {result.run_dir}")


def _check_connector(
    connector: str,
    env: str | None,
    host: str | None,
    username: str | None,
    password: str | None,
    device_type: str | None,
    probe_command: str,
) -> None:
    if not env and not (host and username and password and device_type):
        click.echo(
            f"connector={connector} needs: --host, --username, --password, "
            "--device-type"
        )
        click.echo(
            "or --env=<name>, read from "
            "<NAME>_SANDBOX_HOST/USERNAME/PASSWORD/DEVICE_TYPE."
        )
        return

    connection = _resolve_connection(env, host, username, password, device_type)
    sampler = _build_sampler(connector)
    try:
        sampling.sample(sampler, connection, probe_command)
    except Exception as exc:
        click.echo(f"FAIL: {exc}")
        raise SystemExit(1) from exc
    click.echo("OK")


def _check_provider(provider: str, api_key: str | None, model: str | None) -> None:
    builder = _build_regex_builder(provider, api_key, model)
    context = naming.CliContext(vendor="check", family="check", os="check", version="0")
    try:
        response = builder.build_pattern("show clock", context)
    except Exception as exc:
        click.echo(f"FAIL: {exc}")
        raise SystemExit(1) from exc
    if not response.ready:
        click.echo(f"FAIL: {response.reason or 'response not ready'}")
        raise SystemExit(1)
    click.echo("OK")


@main.command("check")
@click.option("--connector", type=click.Choice(_CONNECTORS), default=None)
@click.option("--provider", type=click.Choice(sorted(_BUILDERS)), default=None)
@click.option(
    "--env",
    default=None,
    help="Named preset: reads <NAME>_SANDBOX_HOST/USERNAME/PASSWORD/DEVICE_TYPE.",
)
@click.option("--host", default=None)
@click.option("--username", default=None)
@click.option("--password", default=None)
@click.option("--device-type", default=None)
@click.option(
    "--probe-command",
    default="show clock",
    show_default=True,
    help="Command sent for a --connector check.",
)
@click.option("--api-key", default=None, help="Used for a --provider check.")
@click.option("--model", default=None, help="Used for a --provider check.")
def check_cmd(
    connector: str | None,
    provider: str | None,
    env: str | None,
    host: str | None,
    username: str | None,
    password: str | None,
    device_type: str | None,
    probe_command: str,
    api_key: str | None,
    model: str | None,
) -> None:
    """Validate a --connector or --provider is reachable, or report what it
    needs. Exactly one of --connector/--provider is required."""
    if bool(connector) == bool(provider):
        raise click.UsageError("specify exactly one of --connector or --provider")
    if connector:
        _check_connector(
            connector, env, host, username, password, device_type, probe_command
        )
    else:
        assert provider is not None
        _check_provider(provider, api_key, model)


@main.command("init-generate-template-config")
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False),
    default="generate-template.yaml",
    show_default=True,
)
@click.option(
    "--force", is_flag=True, default=False, help="Overwrite --out if it already exists."
)
def init_generate_template_config_cmd(out_path: str, force: bool) -> None:
    """Write a placeholder generate-template.yaml to --out, ready to fill in
    and pass to `generate-template --config`."""
    _write_placeholder_config(out_path, force, _GENERATE_TEMPLATE_CONFIG_PLACEHOLDER)


@main.command("generate-template")
@click.option("--connector", type=click.Choice(_CONNECTORS), default=None)
@click.option("--env", default=None)
@click.option("--host", default=None)
@click.option("--username", default=None)
@click.option("--password", default=None)
@click.option("--device-type", default=None)
@click.option(
    "--cmdline", default=None, help="Command to sample when using --connector."
)
@click.option(
    "--sample-file", type=click.Path(exists=True, dir_okay=False), default=None
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
)
@click.option(
    "--provider",
    default=None,
    help='Generation LLM provider (textfsm-ai\'s own registry), e.g. "anthropic".',
)
@click.option("--api-key", default=None)
@click.option("--model", default=None)
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Also write template.textfsm/readable-dsl.txt/recognizers.txt here.",
)
def generate_template_cmd(
    connector: str | None,
    env: str | None,
    host: str | None,
    username: str | None,
    password: str | None,
    device_type: str | None,
    cmdline: str | None,
    sample_file: str | None,
    config_path: str | None,
    provider: str | None,
    api_key: str | None,
    model: str | None,
    out_dir: str | None,
) -> None:
    """One-shot template generation — no trial persisted under trials/.

    Input is exactly one of --sample-file, --connector (+ --cmdline), or
    --config.
    """
    if config_path:
        cfg = cli_config.load_generation_config(Path(config_path))
        connector = connector or cfg.connector
        env = env or cfg.env
        host = host or cfg.host
        username = username or cfg.username
        password = password or cfg.password
        device_type = device_type or cfg.device_type
        cmdline = cmdline or cfg.cmdline
        sample_file = sample_file or cfg.sample_file
        provider = provider or cfg.provider
        api_key = api_key or cfg.api_key
        model = model or cfg.model

    if not provider or not model or not api_key:
        raise click.UsageError(
            "--provider, --api-key, and --model (or a --config supplying all "
            "three) are required"
        )

    if sample_file:
        sample_text = Path(sample_file).read_text(encoding="utf-8")
    elif connector and cmdline:
        connection = _resolve_connection(env, host, username, password, device_type)
        sampler = _build_sampler(connector)
        sample_text = sampling.sample(sampler, connection, cmdline)
    else:
        raise click.UsageError(
            "specify --sample-file, or --connector with --cmdline (and --env "
            "or --host/--username/--password/--device-type), or --config"
        )

    result = generation.generate(sample_text, provider, api_key, model)
    if not result.ready:
        raise click.ClickException(f"generation not ready: {result.reason}")

    click.echo("--- template.textfsm ---")
    click.echo(result.template)
    click.echo("--- readable-dsl.txt ---")
    click.echo(result.readable_dsl)
    click.echo("--- recognizers.txt ---")
    click.echo("\n".join(result.recognizers))

    if out_dir:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "template.textfsm").write_text(result.template, encoding="utf-8")
        (out_path / "readable-dsl.txt").write_text(
            result.readable_dsl, encoding="utf-8"
        )
        (out_path / "recognizers.txt").write_text(
            "\n".join(result.recognizers), encoding="utf-8"
        )
        click.echo(f"written to {out_path}")


@main.command("canonical")
@click.argument("template_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--sample",
    "sample_file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Sample input TEMPLATE_FILE is validated against, to build example records.",
)
def canonical_cmd(template_file: str, sample_file: str) -> None:
    """Print TEMPLATE_FILE's canonical (DSL-compiled) TextFSM text. No LLM call."""
    result = _compile_dsl(template_file, sample_file)
    if not result.ready:
        raise click.ClickException(result.reason)
    click.echo(result.canonical)


@main.command("readable")
@click.argument("template_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--sample",
    "sample_file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Sample input TEMPLATE_FILE is validated against, to build example records.",
)
def readable_cmd(template_file: str, sample_file: str) -> None:
    """Print TEMPLATE_FILE's human-readable DSL description. No LLM call."""
    result = _compile_dsl(template_file, sample_file)
    if not result.ready:
        raise click.ClickException(result.reason)
    click.echo(result.readable)


@main.command("recognizers")
@click.argument("template_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--sample",
    "sample_file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
    help="Sample input TEMPLATE_FILE is validated against, to build example records.",
)
def recognizers_cmd(template_file: str, sample_file: str) -> None:
    """Print TEMPLATE_FILE's recognizer regex patterns, one per line. No LLM
    call."""
    result = _compile_dsl(template_file, sample_file)
    if not result.ready:
        raise click.ClickException(result.reason)
    for pattern in result.recognizers:
        click.echo(pattern)


@main.command("init-trial-config")
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False),
    default="trial.yaml",
    show_default=True,
)
@click.option(
    "--force", is_flag=True, default=False, help="Overwrite --out if it already exists."
)
def init_trial_config_cmd(out_path: str, force: bool) -> None:
    """Write a placeholder trial.yaml to --out, ready to fill in and pass to
    `trial --config`."""
    _write_placeholder_config(out_path, force, _TRIAL_CONFIG_PLACEHOLDER)


@main.command("trial")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.option(
    "--path",
    "store_root_opt",
    default=None,
    help="Overrides the config file's path and the default store root.",
)
def trial_cmd(config_path: str, store_root_opt: str | None) -> None:
    """Run every command in a trial config file (SPEC.md §5 steps 1-7).

    With workers > 1, commands run concurrently via a thread pool. Each
    trial writes to its own run directory, so results don't collide — but
    the shared naming cache (~/.parseforge/.cli-name.json) has no locking,
    so a concurrent cache-miss race across workers can drop one worker's
    newly-learned pattern. Fine for now; a known limitation, not silently
    papered over.
    """
    cfg = cli_config.load_trial_config(Path(config_path))
    store_root = (
        Path(store_root_opt)
        if store_root_opt
        else (Path(cfg.path) if cfg.path else paths.DEFAULT_STORE_ROOT)
    )

    context = naming.CliContext(
        vendor=cfg.vendor, family=cfg.family, os=cfg.os, version=cfg.version
    )
    connection = sampling.DeviceConnection(
        host=cfg.host,
        username=cfg.username,
        password=cfg.password,
        device_type=cfg.device_type,
    )
    naming_builder = _build_regex_builder(cfg.provider, cfg.api_key, cfg.model)
    generation_config = pipeline.LLMProviderConfig(
        provider=cfg.provider, api_key=cfg.api_key, model=cfg.model
    )
    metadata = pipeline.TrialMetadata(
        username=cfg.user, email=cfg.email, description=cfg.description, note=cfg.note
    )
    sampler = _build_sampler(cfg.connector)

    def _run_one(command: str) -> pipeline.TrialResult:
        return pipeline.run_command_pipeline(
            command,
            context,
            connection,
            naming_builder,
            sampler,
            generation_config,
            store_root=store_root,
            metadata=metadata,
        )

    if cfg.workers > 1:
        with ThreadPoolExecutor(max_workers=cfg.workers) as executor:
            results = list(executor.map(_run_one, cfg.commands))
    else:
        results = [_run_one(command) for command in cfg.commands]

    passed_count = 0
    for command, result in zip(cfg.commands, results):
        click.echo(
            f"{command} -> cli_name={result.cli_name} passed={result.passed} "
            f"run_dir={result.run_dir}"
        )
        passed_count += int(result.passed)
    click.echo(f"{passed_count}/{len(results)} passed")


@main.command("integration")
@click.option("--path", "store_root_opt", default=None)
def integration_cmd(store_root_opt: str | None) -> None:
    """Rebuild integration/ for every case under trials/ (SPEC.md §5 step 8)."""
    store_root = Path(store_root_opt) if store_root_opt else paths.DEFAULT_STORE_ROOT
    keys = paths.discover_device_keys(store_root)
    if not keys:
        click.echo(f"no trials found under {store_root}")
        return
    for key in keys:
        reference = integration.build_integration(store_root, key)
        group_count = len(reference)
        variant_count = sum(len(group.variants) for group in reference.values())
        click.echo(
            f"{key.relative_path().as_posix()}: {group_count} group(s), "
            f"{variant_count} variant(s)"
        )
    summary_path = integration.write_reference_summary(store_root)
    click.echo(f"reference-summary.json -> {summary_path}")


@main.command("promotion")
@click.option("--user", required=True)
@click.option("--path", "store_root_opt", default=None)
@click.option("--email", default=None)
@click.option("--description", default=None)
@click.option("--note", default=None)
@click.option(
    "--threshold",
    type=float,
    default=1.0,
    show_default=True,
    help="Minimum match rate (of passed trials) a group needs to auto-promote.",
)
@click.option(
    "--min-samples",
    type=int,
    default=1,
    show_default=True,
    help="Minimum passed-trial count a group needs to auto-promote.",
)
def promotion_cmd(
    user: str,
    store_root_opt: str | None,
    email: str | None,
    description: str | None,
    note: str | None,
    threshold: float,
    min_samples: int,
) -> None:
    """Auto-promote every group that clears its gate (SPEC.md §5 step 9).

    AUTO_PROMOTED mode only — USER_REVIEWED has no CLI surface yet.
    """
    store_root = Path(store_root_opt) if store_root_opt else paths.DEFAULT_STORE_ROOT
    metadata = promotion.PromotionMetadata(
        user=user, email=email, description=description, note=note
    )
    gate = promotion.PromotionGate(
        match_rate_threshold=threshold, min_sample_count=min_samples
    )

    result = promotion.promote_auto(store_root, metadata, gate)

    for promoted_path in result.promoted:
        click.echo(f"promoted: {promoted_path}")
    for evaluation in result.unqualified:
        click.echo(
            f"unqualified: {evaluation.case_key} {evaluation.group_id} "
            f"match_rate={evaluation.match_rate:.2f} "
            f"sample_count={evaluation.sample_count}"
        )
    click.echo(
        f"{len(result.promoted)} promoted, {len(result.unqualified)} unqualified"
    )


if __name__ == "__main__":
    main()
