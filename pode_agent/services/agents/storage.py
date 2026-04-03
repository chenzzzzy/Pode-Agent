"""Agent file storage — manage agent markdown files on disk.

Handles listing, reading, and writing agent configuration files
in ``~/.pode/agents/`` and ``.pode/agents/`` directories.

Reference: docs/subagent-system.md — Agent File Storage
"""

from __future__ import annotations

from pathlib import Path

from pode_agent.infra.logging import get_logger
from pode_agent.services.agents.loader import parse_agent_markdown
from pode_agent.types.agent import AgentConfig, AgentSource

logger = get_logger(__name__)


def list_agent_files(directory: Path) -> list[Path]:
    """List all .md agent files in a directory, sorted by name."""
    if not directory.exists():
        return []
    return sorted(directory.glob("*.md"))


def read_agent_file(file_path: Path) -> AgentConfig | None:
    """Read and parse a single agent markdown file."""
    try:
        content = file_path.read_text(encoding="utf-8")
        return parse_agent_markdown(content, file_path)
    except Exception:
        logger.exception("Failed to read agent file: %s", file_path)
        return None


def load_agents_from_dir(
    directory: Path,
    source: AgentSource = AgentSource.PROJECT,
) -> list[AgentConfig]:
    """Load all agent configs from a directory.

    Returns a list of parsed AgentConfig objects, skipping invalid files.
    """
    configs: list[AgentConfig] = []
    for md_file in list_agent_files(directory):
        config = read_agent_file(md_file)
        if config is not None:
            config.source = source
            configs.append(config)
    return configs
