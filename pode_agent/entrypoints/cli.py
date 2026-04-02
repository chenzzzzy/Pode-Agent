"""CLI entrypoint: ``pode`` command.

Provides the main Typer application with ``--version``, ``--help``,
print mode (positional prompt), and a ``config`` subcommand group.

Reference: docs/modules.md — Entrypoints layer
           docs/api-specs.md — CLI usage
"""

from __future__ import annotations

import asyncio

import typer

from pode_agent import __version__
from pode_agent.core.config import (
    ConfigError,
    get_config_for_cli,
    list_config_for_cli,
    set_config_for_cli,
)

app = typer.Typer(
    name="pode",
    help="Pode-Agent: AI-powered terminal coding assistant.",
    no_args_is_help=False,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"pode-agent {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str | None = typer.Argument(
        None,
        help="Prompt for single-query print mode.",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    model: str = typer.Option(
        "claude-sonnet-4-5-20251101",
        "--model",
        "-m",
        help="Model to use for print mode.",
    ),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        "-f",
        help="Output format: text or json.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show verbose output including tool errors.",
    ),
    safe_mode: bool = typer.Option(
        False,
        "--safe",
        help="Enable safe mode (restricts dangerous operations).",
    ),
) -> None:
    """Pode-Agent: AI-powered terminal coding assistant.

    Run without arguments to start the interactive REPL (Phase 4).
    Pass a prompt string for single-query print mode.
    """
    if ctx.invoked_subcommand is not None:
        return

    if prompt:
        # Print mode: run single query
        from pode_agent.app.print_mode import PrintModeOptions, run_print_mode
        from pode_agent.core.tools.registry import ToolRegistry

        # Collect available tools
        registry = ToolRegistry()
        tools = registry.tools

        opts = PrintModeOptions(
            model=model,
            output_format=output_format,
            verbose=verbose,
            safe_mode=safe_mode,
        )

        exit_code = asyncio.run(run_print_mode(prompt, tools, opts))
        raise typer.Exit(code=exit_code)

    # Phase 4 will add REPL launch here
    typer.echo("Interactive REPL not yet implemented. Use 'pode --help'.")


# --- Config subcommand group ---

config_app = typer.Typer(
    name="config",
    help="Manage configuration values.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(help="Config key (dotted, e.g. 'theme' or 'model_pointers.main')"),
    global_: bool = typer.Option(True, "--global/--project", help="Global or project config."),
) -> None:
    """Get a configuration value."""
    value = get_config_for_cli(key, global_=global_)
    if value is None:
        typer.echo(f"Key not found: {key}", err=True)
        raise typer.Exit(code=1)
    typer.echo(str(value))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key (dotted)"),
    value: str = typer.Argument(help="Value to set"),
    global_: bool = typer.Option(True, "--global/--project", help="Global or project config."),
) -> None:
    """Set a configuration value."""
    try:
        set_config_for_cli(key, value, global_=global_)
        typer.echo(f"Set {key} = {value}")
    except ConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@config_app.command("list")
def config_list(
    global_: bool = typer.Option(True, "--global/--project", help="Global or project config."),
) -> None:
    """List all configuration values."""
    items = list_config_for_cli(global_=global_)
    for k, v in sorted(items.items()):
        typer.echo(f"{k} = {v}")


if __name__ == "__main__":
    app()


def run() -> None:
    """Console script entry point."""
    app()
