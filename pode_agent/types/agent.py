"""SubAgent types — agent configuration, runtime state, and result models.

Reference: docs/subagent-system.md
"""

from __future__ import annotations

import time
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentSource(StrEnum):
    """Where an agent configuration originates (priority: later > earlier)."""

    BUILTIN = "builtin"
    PLUGIN = "plugin"
    USER = "user"
    PROJECT = "project"
    FLAG = "flag"
    POLICY = "policy"


class AgentLocation(StrEnum):
    """Agent location classification."""

    LOCAL = "local"
    REMOTE = "remote"


class AgentModel(StrEnum):
    """Model selection strategy for a sub-agent."""

    INHERIT = "inherit"
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class AgentPermissionMode(StrEnum):
    """Permission behaviour for a sub-agent.

    Values use camelCase for Kode-Agent config file compatibility.
    """

    DEFAULT = "default"
    DONT_ASK = "dontAsk"
    BYPASS_PERMISSIONS = "bypassPermissions"


class AgentConfig(BaseModel):
    """Complete configuration for a single agent type.

    Loaded from markdown files with YAML frontmatter, or from built-in
    definitions.  Merged across sources with priority ordering.
    """

    agent_type: str = Field(description="Agent type name, e.g. 'general-purpose', 'Explore'")
    when_to_use: str = Field(description="Description of when to use this agent")
    tools: list[str] | Literal["*"] = Field(
        default="*",
        description="Available tools list, '*' means all",
    )
    disallowed_tools: list[str] = Field(
        default_factory=list,
        description="Disallowed tools (excluded even when tools='*')",
    )
    skills: list[str] = Field(default_factory=list, description="Associated skills")
    system_prompt: str = Field(default="", description="Agent role system prompt")
    source: AgentSource = AgentSource.BUILTIN
    location: AgentLocation = AgentLocation.LOCAL
    base_dir: str | None = None
    filename: str | None = None
    color: str | None = None
    model: AgentModel = AgentModel.INHERIT
    permission_mode: AgentPermissionMode = AgentPermissionMode.DONT_ASK
    fork_context: bool = Field(
        default=False,
        description="Whether to inherit parent agent context",
    )


class BackgroundAgentStatus(StrEnum):
    """Lifecycle states for a background agent task."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class BackgroundAgentTask(BaseModel):
    """Tracks a background agent task."""

    type: Literal["async_agent"] = "async_agent"
    agent_id: str
    description: str
    prompt: str
    subagent_type: str = "general-purpose"
    status: BackgroundAgentStatus = BackgroundAgentStatus.RUNNING
    started_at: float = Field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None
    result_text: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    total_tool_use_count: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0
    result_retrieved: bool = False


class SubAgentResult(BaseModel):
    """Result returned by a completed sub-agent run."""

    status: Literal["completed", "async_launched"]
    agent_id: str
    description: str
    prompt: str
    content: list[dict[str, Any]] | None = None
    total_tool_use_count: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0
