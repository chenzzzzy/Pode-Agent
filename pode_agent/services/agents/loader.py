"""Agent loader — loads agent configurations from all sources.

Merges agent definitions from:
- Built-in defaults (general-purpose, Explore, Plan)
- Plugin agents
- User agents (~/.pode/agents/)
- Project agents (.pode/agents/)

Reference: docs/subagent-system.md — Agent Loading
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from pode_agent.infra.logging import get_logger
from pode_agent.types.agent import AgentConfig, AgentSource

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Built-in agent definitions
# ---------------------------------------------------------------------------

BUILTIN_AGENTS: dict[str, dict[str, Any]] = {
    "general-purpose": {
        "agent_type": "general-purpose",
        "when_to_use": "General-purpose coding and research tasks",
        "tools": ["*"],
        "disallowed_tools": [],
        "system_prompt": None,
        "source": AgentSource.BUILTIN,
    },
    "Explore": {
        "agent_type": "Explore",
        "when_to_use": "Fast codebase exploration and search tasks",
        "tools": ["*"],
        "disallowed_tools": [],
        "system_prompt": "You are a fast codebase explorer. Focus on finding and understanding code quickly.",
        "source": AgentSource.BUILTIN,
        "model": "haiku",
    },
    "Plan": {
        "agent_type": "Plan",
        "when_to_use": "Planning and architecture decisions",
        "tools": ["*"],
        "disallowed_tools": [],
        "system_prompt": "You are a planning specialist. Analyze requirements and create step-by-step implementation plans.",
        "source": AgentSource.BUILTIN,
    },
}


# ---------------------------------------------------------------------------
# Markdown parsing (YAML frontmatter)
# ---------------------------------------------------------------------------


def parse_agent_markdown(content: str, file_path: Path) -> AgentConfig | None:
    """Parse an agent markdown file with YAML frontmatter.

    Format::

        ---
        agent_type: my-agent
        when_to_use: ...
        tools: ["*"]
        ---

        System prompt body here.
    """
    import re

    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        return None

    yaml_text = match.group(1)
    body = match.group(2).strip()

    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return None

        # Body becomes system_prompt if not explicitly set
        if "system_prompt" not in data and body:
            data["system_prompt"] = body

        data["source"] = data.get("source", AgentSource.PROJECT)
        return AgentConfig(**data)

    except Exception:
        logger.exception("Failed to parse agent markdown: %s", file_path)
        return None


# ---------------------------------------------------------------------------
# Loading & merging
# ---------------------------------------------------------------------------


async def load_agents(
    project_dir: Path | None = None,
    plugin_dirs: list[Path] | None = None,
) -> dict[str, AgentConfig]:
    """Load agent configs from all sources with priority merging.

    Priority (later overrides earlier):
    builtin → plugin → user → project
    """
    agents: dict[str, AgentConfig] = {}

    # 1. Built-in agents
    for name, data in BUILTIN_AGENTS.items():
        agents[name] = AgentConfig(**data)

    # 2. Plugin agents
    if plugin_dirs:
        for plugin_dir in plugin_dirs:
            agents_dir = plugin_dir / "agents"
            if agents_dir.exists():
                for md_file in sorted(agents_dir.glob("*.md")):
                    config = parse_agent_markdown(
                        md_file.read_text(encoding="utf-8"), md_file,
                    )
                    if config:
                        agents[config.agent_type] = config

    # 3. User agents
    user_agents_dir = Path.home() / ".pode" / "agents"
    if user_agents_dir.exists():
        for md_file in sorted(user_agents_dir.glob("*.md")):
            config = parse_agent_markdown(
                md_file.read_text(encoding="utf-8"), md_file,
            )
            if config:
                agents[config.agent_type] = config

    # 4. Project agents
    if project_dir:
        proj_agents_dir = project_dir / ".pode" / "agents"
        if proj_agents_dir.exists():
            for md_file in sorted(proj_agents_dir.glob("*.md")):
                config = parse_agent_markdown(
                    md_file.read_text(encoding="utf-8"), md_file,
                )
                if config:
                    agents[config.agent_type] = config

    return agents


def get_agent_by_type(
    agents: dict[str, AgentConfig],
    type_name: str,
) -> AgentConfig | None:
    """Look up an agent config by type name."""
    return agents.get(type_name)


def merge_agents(
    base: dict[str, AgentConfig],
    override: dict[str, AgentConfig],
) -> dict[str, AgentConfig]:
    """Merge two agent dicts, with override taking priority."""
    return {**base, **override}
