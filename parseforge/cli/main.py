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
def run_cmd(
    vendor: str,
    family: str,
    os_: str,
    version: str,
    provider: str,
    api_key: str | None,
    model: str | None,
    command: tuple[str, ...],
) -> None:
    """Run the pipeline for a single CLI COMMAND against a device (§5)."""
    from parseforge.pipeline import run_command_pipeline

    builder = _build_regex_builder(provider, api_key, model)
    run_command_pipeline(
        " ".join(command),
        key_fields={"vendor": vendor, "family": family, "os": os_, "version": version},
        regex_builder=builder,
    )


if __name__ == "__main__":
    main()
