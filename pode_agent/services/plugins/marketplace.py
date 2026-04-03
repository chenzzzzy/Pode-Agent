"""Marketplace operations — install, uninstall, enable, disable plugins.

Manages the lifecycle of plugins sourced from GitHub, Git, URLs, or
local directories. Supports two install modes:
- ``skill-pack``: copies individual skills/commands into the user's .pode directory
- ``plugin-pack``: copies the entire plugin into the plugins directory

Reference: docs/skill-system.md — Marketplace
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pode_agent.infra.logging import get_logger
from pode_agent.types.skill import InstalledPlugin, PluginManifest

logger = get_logger(__name__)


def _plugins_dir() -> Path:
    """Get the user's plugins directory (~/.pode/plugins/)."""
    d = Path.home() / ".pode" / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _installed_json_path() -> Path:
    """Path to the installed plugins registry."""
    return _plugins_dir() / "installed.json"


def _load_installed() -> dict[str, dict[str, Any]]:
    """Load the installed plugins registry from disk."""
    path = _installed_json_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Failed to load installed plugins registry")
        return {}


def _save_installed(registry: dict[str, dict[str, Any]]) -> None:
    """Save the installed plugins registry to disk."""
    path = _installed_json_path()
    path.write_text(json.dumps(registry, indent=2, default=str), encoding="utf-8")


def list_installed_plugins() -> list[InstalledPlugin]:
    """List all installed plugins."""
    registry = _load_installed()
    result: list[InstalledPlugin] = []
    for plugin_id, data in registry.items():
        try:
            result.append(InstalledPlugin(
                id=plugin_id,
                name=data["name"],
                source=data["source"],
                install_path=Path(data["install_path"]),
                enabled=data.get("enabled", True),
                install_mode=data.get("install_mode", "plugin-pack"),
                installed_at=datetime.fromisoformat(data["installed_at"]),
            ))
        except Exception:
            logger.warning("Invalid installed plugin entry: %s", plugin_id)
    return result


def install_plugin(
    source: str,
    *,
    scope: str = "user",
    install_mode: str = "plugin-pack",
    plugin_name: str | None = None,
) -> InstalledPlugin:
    """Install a plugin from a source path or URL.

    For local directories, copies the plugin into the plugins directory.
    For remote sources, this is a placeholder for future implementation.
    """
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source}")

    # Parse manifest
    manifest_path = source_path / "plugin.json"
    if manifest_path.exists():
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = PluginManifest(**manifest_data)
        name = manifest.name
    else:
        name = plugin_name or source_path.name

    # Install directory
    plugins_base = _plugins_dir()
    install_path = plugins_base / name
    plugin_id = name

    if install_mode == "plugin-pack":
        # Copy entire directory
        if install_path.exists():
            shutil.rmtree(install_path)
        shutil.copytree(source_path, install_path)
    else:
        # skill-pack: just ensure the directory exists
        install_path.mkdir(parents=True, exist_ok=True)

    # Record in registry
    registry = _load_installed()
    now = datetime.now()
    installed = InstalledPlugin(
        id=plugin_id,
        name=name,
        source=source,
        install_path=install_path,
        enabled=True,
        install_mode=install_mode,  # type: ignore[arg-type]
        installed_at=now,
    )
    registry[plugin_id] = installed.model_dump(mode="json")
    _save_installed(registry)

    logger.info("Installed plugin '%s' from %s", name, source)
    return installed


def uninstall_plugin(plugin_id: str) -> None:
    """Uninstall a plugin by ID."""
    registry = _load_installed()
    if plugin_id not in registry:
        raise KeyError(f"Plugin not found: {plugin_id}")

    data = registry[plugin_id]
    install_path = Path(data["install_path"])

    # Remove files
    if install_path.exists():
        shutil.rmtree(install_path, ignore_errors=True)

    # Remove from registry
    del registry[plugin_id]
    _save_installed(registry)

    logger.info("Uninstalled plugin '%s'", plugin_id)


def enable_plugin(plugin_id: str) -> None:
    """Enable a previously disabled plugin."""
    registry = _load_installed()
    if plugin_id not in registry:
        raise KeyError(f"Plugin not found: {plugin_id}")
    registry[plugin_id]["enabled"] = True
    _save_installed(registry)
    logger.info("Enabled plugin '%s'", plugin_id)


def disable_plugin(plugin_id: str) -> None:
    """Disable a plugin without removing it."""
    registry = _load_installed()
    if plugin_id not in registry:
        raise KeyError(f"Plugin not found: {plugin_id}")
    registry[plugin_id]["enabled"] = False
    _save_installed(registry)
    logger.info("Disabled plugin '%s'", plugin_id)
