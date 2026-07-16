"""parseforge CLI entry point."""

from __future__ import annotations

import click

from parseforge import naming


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
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key. Defaults to the ANTHROPIC_API_KEY environment variable; "
    "only needed on a cache miss.",
)
@click.option(
    "--model", default=naming.AnthropicRegexBuilder().model, show_default=True
)
@click.argument("command", nargs=-1, required=True)
def name_cmd(
    vendor: str,
    family: str,
    os_: str,
    version: str,
    api_key: str | None,
    model: str,
    command: tuple[str, ...],
) -> None:
    """Print the canonical cli-name for a raw CLI COMMAND.

    Looked up in the local cache first; only sent to Claude (via
    AnthropicRegexBuilder) on a cache miss.
    """
    context = naming.CliContext(vendor=vendor, family=family, os=os_, version=version)
    builder = naming.AnthropicRegexBuilder(model=model, api_key=api_key)
    click.echo(naming.cli_name(" ".join(command), context, builder=builder))


@main.command("run")
@click.option("--vendor", required=True)
@click.option("--family", required=True)
@click.option("--os", "os_", required=True)
@click.option("--version", required=True)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key. Defaults to the ANTHROPIC_API_KEY environment variable; "
    "only needed on a cache miss.",
)
@click.option(
    "--model", default=naming.AnthropicRegexBuilder().model, show_default=True
)
@click.argument("command", nargs=-1, required=True)
def run_cmd(
    vendor: str,
    family: str,
    os_: str,
    version: str,
    api_key: str | None,
    model: str,
    command: tuple[str, ...],
) -> None:
    """Run the pipeline for a single CLI COMMAND against a device (§5)."""
    from parseforge.pipeline import run_command_pipeline

    builder = naming.AnthropicRegexBuilder(model=model, api_key=api_key)
    run_command_pipeline(
        " ".join(command),
        key_fields={"vendor": vendor, "family": family, "os": os_, "version": version},
        regex_builder=builder,
    )


if __name__ == "__main__":
    main()
