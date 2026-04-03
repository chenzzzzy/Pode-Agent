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
from pode_agent.types.agent import (
    AgentConfig,
    AgentLocation,
    AgentModel,
    AgentPermissionMode,
    AgentSource,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# camelCase → snake_case alias mapping for YAML frontmatter compatibility
# ---------------------------------------------------------------------------

_CAMELCASE_ALIASES: dict[str, str] = {
    "agentType": "agent_type",
    "whenToUse": "when_to_use",
    "disallowedTools": "disallowed_tools",
    "permissionMode": "permission_mode",
    "forkContext": "fork_context",
    "systemPrompt": "system_prompt",
    "subagentType": "subagent_type",
}


def _normalize_aliases(data: dict[str, Any]) -> dict[str, Any]:
    """Convert camelCase YAML keys to snake_case Python field names."""
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        python_key = _CAMELCASE_ALIASES.get(key, key)
        normalized[python_key] = value
    return normalized


# ---------------------------------------------------------------------------
# Built-in agent definitions
# ---------------------------------------------------------------------------

BUILTIN_AGENTS: list[AgentConfig] = [
    AgentConfig(
        agent_type="general-purpose",
        when_to_use="General-purpose coding and research tasks",
        tools="*",
        disallowed_tools=[],
        system_prompt=(
            "You are a general-purpose agent. You can use all available tools "
            "to accomplish tasks. Be thorough and methodical."
        ),
        source=AgentSource.BUILTIN,
        location=AgentLocation.LOCAL,
        model=AgentModel.INHERIT,
        permission_mode=AgentPermissionMode.DONT_ASK,
        fork_context=False,
    ),
    AgentConfig(
        agent_type="Explore",
        when_to_use="Fast codebase exploration and search tasks",
        tools="*",
        disallowed_tools=["Task", "FileEditTool", "FileWriteTool", "BashTool"],
        system_prompt=(
            "You are a code search expert. Use Glob, Grep and FileRead "
            "to quickly find files and code. Only research — never modify files."
        ),
        source=AgentSource.BUILTIN,
        location=AgentLocation.LOCAL,
        model=AgentModel.HAIKU,
        permission_mode=AgentPermissionMode.DONT_ASK,
        fork_context=False,
    ),
    AgentConfig(
        agent_type="Plan",
        when_to_use="Architecture planning and design analysis",
        tools="*",
        disallowed_tools=["Task", "FileEditTool", "FileWriteTool", "BashTool"],
        system_prompt=(
            "You are an architecture planning specialist. Analyze code "
            "structure and create step-by-step implementation plans."
        ),
        source=AgentSource.BUILTIN,
        location=AgentLocation.LOCAL,
        model=AgentModel.INHERIT,
        permission_mode=AgentPermissionMode.DONT_ASK,
        fork_context=False,
    ),
]


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
        raw_data = yaml.safe_load(yaml_text)
        if not isinstance(raw_data, dict):
            return None

        # Normalize camelCase aliases
        data = _normalize_aliases(raw_data)

        # Body becomes system_prompt if not explicitly set
        if "system_prompt" not in data and body:
            data["system_prompt"] = body

        data["source"] = data.get("source", AgentSource.PROJECT)
        data["location"] = data.get("location", AgentLocation.LOCAL)
        data.setdefault("base_dir", str(file_path.parent))
        data.setdefault("filename", file_path.name)

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
    for config in BUILTIN_AGENTS:
        agents[config.agent_type] = config

    # 2. Plugin agents
    if plugin_dirs:
        for plugin_dir in plugin_dirs:
            agents_dir = plugin_dir / "agents"
            if agents_dir.exists():
                for md_file in sorted(agents_dir.glob("*.md")):
                    parsed = parse_agent_markdown(
                        md_file.read_text(encoding="utf-8"), md_file,
                    )
                    if parsed is not None:
                        agents[parsed.agent_type] = parsed

    # 3. User agents (~/.pode/agents/)
    user_agents_dir = Path.home() / ".pode" / "agents"
    if user_agents_dir.exists():
        for md_file in sorted(user_agents_dir.glob("*.md")):
            parsed = parse_agent_markdown(
                md_file.read_text(encoding="utf-8"), md_file,
            )
            if parsed is not None:
                parsed.source = AgentSource.USER
                agents[parsed.agent_type] = parsed

    # 4. Project agents (.pode/agents/)
    if project_dir:
        proj_agents_dir = project_dir / ".pode" / "agents"
        if proj_agents_dir.exists():
            for md_file in sorted(proj_agents_dir.glob("*.md")):
                parsed = parse_agent_markdown(
                    md_file.read_text(encoding="utf-8"), md_file,
                )
                if parsed is not None:
                    parsed.source = AgentSource.PROJECT
                    agents[parsed.agent_type] = parsed

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
