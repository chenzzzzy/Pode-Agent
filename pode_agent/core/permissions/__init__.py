"""Permission system: engine, rules, and types.

Public API re-exports for convenient imports::

    from pode_agent.core.permissions import PermissionEngine, is_safe_bash_command

Reference: docs/api-specs.md — Permissions API
"""

from pode_agent.core.permissions.engine import PermissionEngine
from pode_agent.core.permissions.rules.bash import is_safe_bash_command
from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.permissions.store import apply_context_update
from pode_agent.core.permissions.types import (
    PermissionContext,
    PermissionDecision,
    PermissionMode,
    PermissionResult,
    ToolPermissionContext,
)

__all__ = [
    "PermissionContext",
    "PermissionDecision",
    "PermissionEngine",
    "PermissionMode",
    "PermissionResult",
    "ToolPermissionContext",
    "apply_context_update",
    "is_path_in_working_directories",
    "is_safe_bash_command",
]
