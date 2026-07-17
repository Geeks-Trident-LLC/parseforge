"""parseforge CLI entry point."""

from __future__ import annotations

import click

from parseforge import naming

_BUILDERS: dict[str, type[naming.RegexBuilder]] = {
    "anthropic": naming.AnthropicRegexBuilder,
    "deepseek": naming.DeepSeekRegexBuilder,
}


def _build_regex_builder(
    provider: str, api_key: str | None, model: str | None
) -> naming.RegexBuilder:
    kwargs: dict[str, str] = {}
    if api_key is not None:
        kwargs["api_key"] = api_key
    if model is not None:
        kwargs["model"] = model
    return _BUILDERS[provider](**kwargs)


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
    "variable (ANTHROPIC_API_KEY, DEEPSEEK_API_KEY); only needed on a cache miss.",
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
    "--generation-provider",
    required=True,
    help="LLM provider for template generation (textfsm-ai's own registry, "
    'e.g. "anthropic", "deepseek").',
)
@click.option(
    "--generation-api-key",
    required=True,
    help="API key for the template-generation LLM call.",
)
@click.option(
    "--generation-model",
    required=True,
    help="Model for the template-generation LLM call.",
)
@click.option(
    "--store-root",
    default=None,
    help="Root directory for trial output. Defaults to ~/.parseforge/tests.",
)
@click.option("--project", default=None)
@click.option("--username-ref", "user_reference", default=None)
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
    generation_provider: str,
    generation_api_key: str,
    generation_model: str,
    store_root: str | None,
    project: str | None,
    user_reference: str | None,
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
        provider=generation_provider, api_key=generation_api_key, model=generation_model
    )
    metadata = TrialMetadata(
        project=project,
        username=username,
        user_reference=user_reference,
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


if __name__ == "__main__":
    main()
