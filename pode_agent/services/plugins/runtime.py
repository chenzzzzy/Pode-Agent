"""Plugin runtime — load plugin.json manifests and configure session plugins.

Resolves plugin directories, parses manifests, validates them, and
produces a list of ``SessionPlugin`` objects for use by the session.

Reference: docs/skill-system.md — Plugin 架构
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pode_agent.infra.logging import get_logger
from pode_agent.services.plugins.commands import reload_custom_commands
from pode_agent.services.plugins.validation import validate_plugin_json
from pode_agent.types.skill import PluginManifest

logger = get_logger(__name__)


class SessionPlugin(BaseModel):
    """A loaded plugin with resolved paths, ready for session use."""

    manifest: PluginManifest
    plugin_dir: Path
    enabled: bool = True

    @property
    def name(self) -> str:
        return self.manifest.name

    def skill_dirs(self) -> list[Path]:
        """Return resolved skill directories."""
        return [
            self.plugin_dir / s
            for s in self.manifest.skills
            if (self.plugin_dir / s).is_dir()
        ]

    def command_dirs(self) -> list[Path]:
        """Return resolved command directories."""
        return [
            self.plugin_dir / c
            for c in self.manifest.commands
            if (self.plugin_dir / c).is_dir()
        ]

    def agent_dirs(self) -> list[Path]:
        """Return resolved agent config directories."""
        return [
            self.plugin_dir / a
            for a in self.manifest.agents
            if (self.plugin_dir / a).is_dir()
        ]


def load_plugin_from_dir(plugin_dir: Path) -> SessionPlugin | None:
    """Load a single plugin from a directory containing .pode-plugin/plugin.json.

    Returns None if the directory is not a valid plugin.
    """
    manifest_path = plugin_dir / ".pode-plugin" / "plugin.json"
    if not manifest_path.exists():
        # Also check for top-level plugin.json (simpler plugin layout)
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            logger.debug("No plugin.json found in %s", plugin_dir)
            return None

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read plugin manifest %s: %s", manifest_path, e)
        return None

    # Validate
    errors = validate_plugin_json(data)
    if errors:
        for err in errors:
            logger.warning("Plugin validation error in %s: %s", manifest_path, err)
        return None

    try:
        manifest = PluginManifest(**data)
    except Exception as e:
        logger.warning("Failed to parse plugin manifest %s: %s", manifest_path, e)
        return None

    return SessionPlugin(
        manifest=manifest,
        plugin_dir=plugin_dir,
        enabled=True,
    )


async def configure_session_plugins(
    plugin_dirs: list[str | Path] | None = None,
    installed_plugins: list[dict[str, Any]] | None = None,
) -> list[SessionPlugin]:
    """Load and configure all plugins for a session.

    Args:
        plugin_dirs: Explicit plugin directory paths (supports glob patterns).
        installed_plugins: Registry entries from marketplace (install_path, enabled).

    Returns:
        List of loaded SessionPlugin objects.

    Reference: docs/skill-system.md — Plugin 加载流程
    """
    plugins: list[SessionPlugin] = []
    seen_dirs: set[Path] = set()

    # 1. Load from explicit plugin_dirs
    if plugin_dirs:
        for dir_str in plugin_dirs:
            p = Path(dir_str)
            if p.is_dir() and p.resolve() not in seen_dirs:
                seen_dirs.add(p.resolve())
                plugin = load_plugin_from_dir(p)
                if plugin is not None:
                    plugins.append(plugin)

    # 2. Load from installed plugins registry
    if installed_plugins:
        for entry in installed_plugins:
            install_path = Path(entry.get("install_path", ""))
            if not install_path.is_dir():
                continue
            if install_path.resolve() in seen_dirs:
                continue
            seen_dirs.add(install_path.resolve())

            plugin = load_plugin_from_dir(install_path)
            if plugin is not None:
                plugin.enabled = entry.get("enabled", True)
                plugins.append(plugin)

    # 3. Invalidate command cache so next load picks up plugin commands/skills
    reload_custom_commands()

    logger.info("Loaded %d plugins", len(plugins))
    return plugins
