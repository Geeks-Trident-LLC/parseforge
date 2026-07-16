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
@click.argument("command", nargs=-1, required=True)
def name_cmd(
    vendor: str, family: str, os_: str, version: str, command: tuple[str, ...]
) -> None:
    """Print the canonical cli-name for a raw CLI COMMAND.

    Looked up in the local cache first; only sent to an LLM (via a
    RegexBuilder) on a cache miss. No RegexBuilder is wired into the
    scaffold yet, so this only succeeds for commands already in
    ~/.parseforge/.cli-name.json until one is implemented.
    """
    context = naming.CliContext(vendor=vendor, family=family, os=os_, version=version)
    click.echo(naming.cli_name(" ".join(command), context))


@main.command("run")
@click.option("--vendor", required=True)
@click.option("--family", required=True)
@click.option("--os", "os_", required=True)
@click.option("--version", required=True)
@click.argument("command", nargs=-1, required=True)
def run_cmd(
    vendor: str, family: str, os_: str, version: str, command: tuple[str, ...]
) -> None:
    """Run the pipeline for a single CLI COMMAND against a device (§5)."""
    from parseforge.pipeline import run_command_pipeline

    run_command_pipeline(
        " ".join(command),
        key_fields={"vendor": vendor, "family": family, "os": os_, "version": version},
    )


if __name__ == "__main__":
    main()
