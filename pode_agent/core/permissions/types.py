"""Permission system types and enums.

Defines the core data models for the permission system: modes, results,
decisions, and the permission context used by the engine.

Reference: docs/api-specs.md — Permissions API
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PermissionMode(StrEnum):
    """Tool execution permission modes."""

    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypass_permissions"


class PermissionResult(StrEnum):
    """Outcome of a permission check."""

    ALLOWED = "allowed"
    NEEDS_PROMPT = "needs_prompt"
    DENIED = "denied"


class PermissionDecision(StrEnum):
    """User's response to a permission prompt."""

    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"
    ALLOW_ALWAYS = "allow_always"
    DENY = "deny"


class ToolPermissionContext(BaseModel):
    """Runtime permission state for a session.

    Tracks which tools have been approved or rejected for the current
    session, along with rule-based permissions from project config.
    """

    approved_tools: set[str] = Field(default_factory=set)
    rejected_tools: set[str] = Field(default_factory=set)


class PermissionContext(BaseModel):
    """Full context passed to the permission engine for evaluation.

    Combines the session permission state, project-level rules, and
    the current permission mode.
    """

    mode: PermissionMode = PermissionMode.DEFAULT
    tool_permission_context: ToolPermissionContext = Field(
        default_factory=ToolPermissionContext,
    )
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
