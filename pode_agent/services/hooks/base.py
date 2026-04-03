"""Hook base types — configuration, result, and state models.

Hooks extend Pode-Agent's behaviour at four lifecycle injection points:
- **UserPromptSubmit**: before the user prompt reaches the LLM
- **PreToolUse**: before a tool executes (can block or modify inputs)
- **PostToolUse**: after a tool executes (can modify results)
- **Stop**: when the agentic loop would terminate (can force continuation)

Hooks come in two flavours:
- **Command hooks**: external processes that receive JSON on stdin and return JSON on stdout
- **Prompt hooks**: LLM calls that evaluate and respond with structured output

Reference: docs/hooks.md — Hook System Specification
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Hook event types (match the 4 injection points)
# ---------------------------------------------------------------------------


class HookEvent(StrEnum):
    """Lifecycle event that triggers a hook."""

    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"


# ---------------------------------------------------------------------------
# Hook result — returned by each hook execution
# ---------------------------------------------------------------------------


class HookResult(BaseModel):
    """Outcome of executing one or more hooks at an injection point.

    Aggregation rule: if any hook returns ``block``, the final result is
    ``block``.  Otherwise, if any hook returns ``modify``, the final result
    is ``modify``.  Otherwise ``continue``.
    """

    action: Literal["continue", "block", "modify"] = "continue"
    message: str | None = None
    modified_data: Any = None
    additional_system_prompt: str | None = None
    permission_decision: Literal["allow", "deny", "ask", "passthrough"] | None = None


# ---------------------------------------------------------------------------
# Hook state — carried across injection points within a single query
# ---------------------------------------------------------------------------


class HookState(BaseModel):
    """Mutable state carried through a single ``query_core()`` invocation.

    Tracks system prompts injected by hooks and whether user-prompt hooks
    have already fired (to avoid re-running on recursive re-entry).
    """

    additional_system_prompts: list[str] = Field(default_factory=list)
    user_prompt_hooks_ran: bool = False
    hook_configs: list[HookConfig] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Hook configuration — loaded from settings files
# ---------------------------------------------------------------------------


class HookConfig(BaseModel):
    """A single hook definition from project or user settings.

    Matches the JSON structure in ``.pode/settings.json`` hooks array.
    """

    event: HookEvent
    matcher: str = "all"  # glob pattern or "all"
    type: Literal["command", "prompt"] = "command"
    command: list[str] | None = None  # for command hooks: ["node", "script.js"]
    prompt_text: str | None = None  # for prompt hooks
    timeout_ms: int = 30000


# ---------------------------------------------------------------------------
# Payloads sent to hook processes via JSON on stdin
# ---------------------------------------------------------------------------


class UserPromptSubmitPayload(BaseModel):
    """JSON payload for UserPromptSubmit hooks."""

    prompt: str
    messages: list[dict[str, Any]]


class PreToolUsePayload(BaseModel):
    """JSON payload for PreToolUse hooks."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


class PostToolUsePayload(BaseModel):
    """JSON payload for PostToolUse hooks."""

    tool_name: str
    tool_input: dict[str, Any]
    tool_result: str
    tool_use_id: str
    is_error: bool = False


class StopPayload(BaseModel):
    """JSON payload for Stop hooks."""

    messages: list[dict[str, Any]]
    stop_reason: str | None = None
