"""SubAgent types — agent configuration, runtime state, and result models.

Reference: docs/subagent-system.md
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class AgentSource(StrEnum):
    """Where an agent configuration originates (priority: later > earlier)."""

    BUILTIN = "builtin"
    PLUGIN = "plugin"
    USER = "user"
    PROJECT = "project"
    FLAG = "flag"
    POLICY = "policy"


class AgentModel(StrEnum):
    """Model selection strategy for a sub-agent."""

    INHERIT = "inherit"
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


class AgentPermissionMode(StrEnum):
    """Permission behaviour for a sub-agent."""

    DEFAULT = "default"
    DONT_ASK = "dont_ask"
    BYPASS_PERMISSIONS = "bypass_permissions"


class AgentConfig(BaseModel):
    """Complete configuration for a single agent type.

    Loaded from markdown files with YAML frontmatter, or from built-in
    definitions.  Merged across sources with priority ordering.
    """

    agent_type: str
    when_to_use: str | None = None
    tools: list[str] = Field(default_factory=lambda: ["*"])
    disallowed_tools: list[str] = Field(default_factory=list)
    system_prompt: str | None = None
    source: AgentSource = AgentSource.BUILTIN
    model: AgentModel = AgentModel.INHERIT
    permission_mode: AgentPermissionMode = AgentPermissionMode.DEFAULT
    fork_context: bool = False
    skills: list[str] | None = None
    color: str | None = None


class SubAgentResult(BaseModel):
    """Result returned by a completed sub-agent run."""

    status: Literal["success", "error", "async_launched"]
    agent_id: str
    description: str
    prompt: str
    content: str | None = None
    total_tool_use_count: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0


class BackgroundAgentStatus(StrEnum):
    """Lifecycle states for a background agent task."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class BackgroundAgentTask(BaseModel):
    """Tracks a background agent task."""

    agent_id: str
    description: str
    prompt: str
    subagent_type: str = "general-purpose"
    status: BackgroundAgentStatus = BackgroundAgentStatus.RUNNING
    result_text: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=datetime.now)
    completed_at: datetime | None = None
    total_tool_use_count: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0
    result_retrieved: bool = False
