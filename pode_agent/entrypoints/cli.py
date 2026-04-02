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
from pode_agent.core.config.schema import DEFAULT_MODEL_NAME

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
        DEFAULT_MODEL_NAME,
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
        from pode_agent.core.tools.loader import ToolLoader
        from pode_agent.core.tools.registry import ToolRegistry

        # Collect available tools
        registry = ToolRegistry()
        loader = ToolLoader(registry)
        loader._load_builtin_tools()
        tools = registry.tools

        opts = PrintModeOptions(
            model=model,
            output_format=output_format,
            verbose=verbose,
            safe_mode=safe_mode,
        )

        exit_code = asyncio.run(run_print_mode(prompt, tools, opts))
        raise typer.Exit(code=exit_code)

    # Interactive REPL: spawn Bun + Ink UI with JSON-RPC bridge
    exit_code = asyncio.run(_launch_repl(model=model, safe_mode=safe_mode))
    raise typer.Exit(code=exit_code)


# --- REPL launcher ---


async def _launch_repl(*, model: str = DEFAULT_MODEL_NAME, safe_mode: bool = False) -> int:
    """Launch the interactive REPL: Bun Ink UI + Python JSON-RPC bridge.

    Architecture::

        Python (parent)  ─── pipe stdin/stdout ───  Bun (child, Ink UI)
        UIBridge reads from Bun.stdout, writes to Bun.stdin
        Bun reads from pipe.stdin, writes to pipe.stdout

    Steps:
        1. Check Bun is installed
        2. Locate the Ink UI entry point (src/ui/src/index.tsx)
        3. Spawn Bun as child process with stdin/stdout piped
        4. Run UIBridge using the child process's stdin/stdout
        5. Clean up on exit
    """
    import shutil
    from pathlib import Path

    # Check Bun installation
    bun_path = shutil.which("bun")
    if bun_path is None:
        typer.echo(
            "Error: Bun is required for the interactive REPL but not found.\n"
            "Install from https://bun.sh",
            err=True,
        )
        return 1

    # Locate UI entry point — look relative to this package
    package_dir = Path(__file__).resolve().parent.parent.parent  # project root
    ui_entry = package_dir / "src" / "ui" / "src" / "index.tsx"
    if not ui_entry.exists():
        typer.echo(
            f"Error: UI entry point not found at {ui_entry}\n"
            "Make sure the src/ui/ directory exists.",
            err=True,
        )
        return 1

    # Check node_modules
    ui_dir = package_dir / "src" / "ui"
    if not (ui_dir / "node_modules").exists():
        typer.echo("Installing UI dependencies...", err=True)
        install_proc = await asyncio.create_subprocess_exec(
            bun_path, "install",
            cwd=str(ui_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await install_proc.wait()
        if install_proc.returncode != 0:
            typer.echo("Error: Failed to install UI dependencies.", err=True)
            return 1

    # Spawn Bun process
    proc = await asyncio.create_subprocess_exec(
        bun_path, "run", str(ui_entry),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ui_dir),
    )

    if proc.stdin is None or proc.stdout is None:
        typer.echo("Error: Failed to pipe Bun process stdin/stdout.", err=True)
        return 1

    # Run UI bridge — read from Bun's stdout, write to Bun's stdin
    from pode_agent.entrypoints.ui_bridge import UIBridge

    bridge = UIBridge(
        read_stream=proc.stdout,
        write_stream=proc.stdin,
    )

    try:
        await bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()

    return proc.returncode or 0


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
