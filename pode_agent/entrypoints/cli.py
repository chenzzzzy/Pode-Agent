"""CLI entrypoint: ``pode`` command.

Provides the main Typer application with ``--version``, ``--help``,
print mode (positional prompt), and a ``config`` subcommand group.

Reference: docs/modules.md — Entrypoints layer
           docs/api-specs.md — CLI usage
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from pode_agent import __version__
from pode_agent.core.config import (
    ConfigError,
    get_config_for_cli,
    list_config_for_cli,
    set_config_for_cli,
)
from pode_agent.core.config.schema import DEFAULT_MODEL_NAME

# Load .env from the current working directory before any LLM calls
load_dotenv(Path.cwd() / ".env")

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
        from pode_agent.core.config.loader import get_global_config
        from pode_agent.core.tools.loader import ToolLoader
        from pode_agent.core.tools.registry import ToolRegistry

        async def _run_print(
            p: str, opts: PrintModeOptions,
        ) -> int:
            config = get_global_config()
            registry = ToolRegistry()
            loader = ToolLoader(registry, config=config)
            await loader.load_all()
            tools = registry.tools
            return await run_print_mode(p, tools, opts)

        opts = PrintModeOptions(
            model=model,
            output_format=output_format,
            verbose=verbose,
            safe_mode=safe_mode,
        )

        exit_code = asyncio.run(_run_print(prompt, opts))
        raise typer.Exit(code=exit_code)

    # Interactive REPL: spawn Bun + Ink UI with JSON-RPC bridge
    exit_code = asyncio.run(_launch_repl(model=model, safe_mode=safe_mode))
    raise typer.Exit(code=exit_code)


# --- REPL launcher ---


async def _launch_repl(*, model: str = DEFAULT_MODEL_NAME, safe_mode: bool = False) -> int:
    """Launch the interactive REPL: Bun Ink UI + Python JSON-RPC bridge.

    Architecture::

        Python (parent)  ─── TCP socket (JSON-RPC) ───  Bun (child, Ink UI)
        UIBridge listens on a port, Bun connects to it
        Bun's stdin/stdout remain connected to TTY for user input

    Steps:
        1. Start TCP server on random port for JSON-RPC
        2. Check Bun is installed
        3. Locate the Ink UI entry point (src/ui/src/index.tsx)
        4. Spawn Bun as child process with PODE_RPC_PORT env var
        5. Accept connection from Bun and run UIBridge
        6. Clean up on exit
    """
    import shutil
    import socket
    from pathlib import Path

    # Start TCP server for JSON-RPC
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))  # Bind to random port
    server.listen(1)
    rpc_port = server.getsockname()[1]
    server.setblocking(False)

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

    # Spawn Bun process with TTY stdin/stdout and RPC port
    # Bun inherits the parent's TTY for user input
    proc = await asyncio.create_subprocess_exec(
        bun_path, "run", str(ui_entry),
        stdin=None,   # inherit TTY
        stdout=None,  # inherit TTY
        stderr=None,  # inherit TTY
        cwd=str(ui_dir),
        env={**os.environ, "PODE_RPC_PORT": str(rpc_port)},
    )

    # Wait for Bun to connect to our RPC server
    try:
        loop = asyncio.get_event_loop()
        conn, _addr = await asyncio.wait_for(
            loop.sock_accept(server),
            timeout=30.0,
        )
    except TimeoutError:
        typer.echo("Error: Timed out waiting for UI to connect.", err=True)
        if proc.returncode is None:
            proc.kill()
        return 1

    # Wrap the accepted socket for async I/O
    # connect_accepted_socket returns (transport, protocol)
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await loop.connect_accepted_socket(lambda: protocol, conn)

    # Create StreamWriter with the transport (not the raw socket!)
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)

    # Run UI bridge — read/write via the socket
    from pode_agent.entrypoints.ui_bridge import UIBridge

    bridge = UIBridge(
        read_stream=reader,
        write_stream=writer,
    )

    try:
        await bridge.run()
    except KeyboardInterrupt:
        pass
    finally:
        writer.close()
        await writer.wait_closed()
        server.close()
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


# --- Plugin subcommand group (Phase 5) ---

plugin_app = typer.Typer(
    name="plugin",
    help="Manage plugins and skills.",
    no_args_is_help=True,
)
app.add_typer(plugin_app, name="plugin")


@plugin_app.command("install")
def plugin_install(
    source: str = typer.Argument(help="Plugin source path or URL"),
    scope: str = typer.Option("user", "--scope", help="Installation scope: user or project"),
    name: str | None = typer.Option(None, "--name", help="Override plugin name"),
) -> None:
    """Install a plugin from a source path."""
    from pode_agent.services.plugins.marketplace import install_plugin

    try:
        installed = install_plugin(source, scope=scope, plugin_name=name)
        typer.echo(f"Installed plugin: {installed.name} (v{installed.install_mode})")
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@plugin_app.command("uninstall")
def plugin_uninstall(
    plugin_id: str = typer.Argument(help="Plugin ID to uninstall"),
) -> None:
    """Uninstall a plugin."""
    from pode_agent.services.plugins.marketplace import uninstall_plugin

    try:
        uninstall_plugin(plugin_id)
        typer.echo(f"Uninstalled plugin: {plugin_id}")
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@plugin_app.command("enable")
def plugin_enable(
    plugin_id: str = typer.Argument(help="Plugin ID to enable"),
) -> None:
    """Enable a disabled plugin."""
    from pode_agent.services.plugins.marketplace import enable_plugin

    try:
        enable_plugin(plugin_id)
        typer.echo(f"Enabled plugin: {plugin_id}")
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@plugin_app.command("disable")
def plugin_disable(
    plugin_id: str = typer.Argument(help="Plugin ID to disable"),
) -> None:
    """Disable a plugin without removing it."""
    from pode_agent.services.plugins.marketplace import disable_plugin

    try:
        disable_plugin(plugin_id)
        typer.echo(f"Disabled plugin: {plugin_id}")
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@plugin_app.command("list")
def plugin_list(
    scope: str = typer.Option("user", "--scope", help="Filter by scope: user or project"),
) -> None:
    """List all installed plugins."""
    from pode_agent.services.plugins.marketplace import list_installed_plugins

    plugins = list_installed_plugins()
    if not plugins:
        typer.echo("No plugins installed.")
        return

    for p in plugins:
        status = "enabled" if p.enabled else "disabled"
        typer.echo(f"  {p.name} [{status}] ({p.install_mode}) from {p.source}")


@plugin_app.command("refresh")
def plugin_refresh() -> None:
    """Refresh skill and command cache."""
    from pode_agent.services.plugins.commands import reload_custom_commands

    reload_custom_commands()
    typer.echo("Cache refreshed.")


# --- Marketplace subcommand group ---

marketplace_app = typer.Typer(
    name="marketplace",
    help="Manage marketplace sources.",
    no_args_is_help=True,
)
plugin_app.add_typer(marketplace_app, name="marketplace")


@marketplace_app.command("add")
def marketplace_add(
    source: str = typer.Argument(
        help="Marketplace source (e.g. github:owner/repo, file:./path)",
    ),
    name: str | None = typer.Option(None, "--name", help="Override marketplace name"),
    ref: str = typer.Option("main", "--ref", help="Git ref to use"),
) -> None:
    """Add a marketplace source."""
    from pode_agent.services.plugins.marketplace import add_marketplace

    try:
        entry = add_marketplace(source, name=name, ref=ref)
        src_info = entry.get("source", {}).get("url") or source
        typer.echo(f"Added marketplace: {src_info}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@marketplace_app.command("remove")
def marketplace_remove(
    name: str = typer.Argument(help="Marketplace name to remove"),
) -> None:
    """Remove a marketplace source."""
    from pode_agent.services.plugins.marketplace import remove_marketplace

    try:
        remove_marketplace(name)
        typer.echo(f"Removed marketplace: {name}")
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None


@marketplace_app.command("list")
def marketplace_list() -> None:
    """List all known marketplaces."""
    from pode_agent.services.plugins.marketplace import list_marketplaces

    marketplaces = list_marketplaces()
    if not marketplaces:
        typer.echo("No marketplaces configured.")
        return

    for mkt in marketplaces:
        source = mkt.get("source", {})
        src_type = source.get("type", "unknown")
        src_url = source.get("url") or source.get("path", "")
        typer.echo(f"  {mkt['name']} ({src_type}:{src_url})")


@marketplace_app.command("update")
def marketplace_update(
    name: str = typer.Argument(help="Marketplace name to update"),
) -> None:
    """Update marketplace cache."""
    from pode_agent.services.plugins.marketplace import update_marketplace

    try:
        update_marketplace(name)
        typer.echo(f"Updated marketplace: {name}")
    except KeyError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from None

