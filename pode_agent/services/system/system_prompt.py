"""System prompt assembly for the Agentic Loop.

Dynamically composes the full system prompt from multiple sections:
1. Base personality prompt
2. CWD (current working directory)
3. Plan mode instructions (when active)
4. Tool reminders (available tools summary)
5. Active plan context (when executing a plan)
6. Todo list (when todos exist)
7. Project context (git status, directory structure, README, project docs)
8. System reminders (mention-derived, instruction file notes)

Reference: docs/agent-loop.md — System Prompt
Reference: Kode-Agent ``src/services/system/systemPrompt.ts``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pode_agent.core.permissions.types import PermissionMode
    from pode_agent.core.tools.base import Tool
    from pode_agent.types.plan import Plan

BASE_SYSTEM_PROMPT = """\
You are Pode, an AI-powered terminal coding assistant.

You help users with software engineering tasks: writing code, debugging,
refactoring, running tests, and managing projects.

Key behaviors:
- Be concise and direct in your responses.
- Use tools to accomplish tasks rather than asking the user to do things manually.
- Read files before modifying them.
- Validate your changes by running relevant tests or type checkers.
- Never hardcode secrets or credentials in source code.
"""

CWD_TEMPLATE = """

Current working directory: {cwd}
Current date/time: {datetime}
"""

PLAN_MODE_SYSTEM_PROMPT = """

<plan_mode>
You are now in **plan mode**. In this mode:
1. You MUST only use read-only tools (file_read, glob, grep, ls, bash for safe commands).
2. Do NOT modify any files or execute side-effect commands.
3. Explore the codebase thoroughly to understand the current state.
4. When ready, call the `exit_plan_mode` tool with a complete Plan object.
5. The plan MUST include: objective, steps (with suggested tools), acceptance criteria, and risks.
</plan_mode>
"""

TOOL_REMINDERS_TEMPLATE = """

<available_tools>
You have access to the following tools:
{tool_list}
</available_tools>
"""

ACTIVE_PLAN_TEMPLATE = """

<active_plan>
You are executing the following plan:
Objective: {objective}
Status: {status}

Steps:
{steps}
</active_plan>
"""

TODO_CONTEXT_TEMPLATE = """

<todos>
Current task list:
{todo_list}
</todos>
"""


def build_system_prompt(
    base: str,
    cwd: str,
    *,
    permission_mode: PermissionMode | None = None,
    tools: list[Tool] | None = None,
    plan: Plan | None = None,
    todos: list[dict[str, Any]] | None = None,
    project_context: dict[str, str] | None = None,
    system_reminders: list[str] | None = None,
) -> str:
    """Assemble the full system prompt from multiple sections.

    Args:
        base: Base personality prompt text.
        cwd: Current working directory.
        permission_mode: Current permission mode (adds plan mode instructions).
        tools: Available tools (adds tool reminders).
        plan: Active plan (adds plan execution context).
        todos: Current todo items (adds todo context).
        project_context: Project context dict (injected as XML context tags).
        system_reminders: Extra system reminder strings (mention-derived, etc.).

    Returns:
        Fully assembled system prompt string.
    """
    parts = [base]

    # 1. CWD + current date/time
    if cwd:
        from datetime import datetime

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        parts.append(CWD_TEMPLATE.format(cwd=cwd, datetime=now_str))

    # 2. Plan mode instructions
    if permission_mode is not None:
        from pode_agent.core.permissions.types import PermissionMode

        if permission_mode == PermissionMode.PLAN:
            parts.append(PLAN_MODE_SYSTEM_PROMPT)

    # 3. Tool reminders
    if tools:
        tool_lines = []
        for t in tools:
            desc = (t.description or "")[:80]
            tool_lines.append(f"- {t.name}: {desc}")
        parts.append(TOOL_REMINDERS_TEMPLATE.format(tool_list="\n".join(tool_lines)))

    # 4. Active plan context
    if plan is not None:
        step_lines = []
        for step in plan.steps:
            marker = {
                "pending": "[ ]",
                "running": "[>]",
                "done": "[x]",
                "skipped": "[-]",
                "failed": "[!]",
            }.get(step.status, "[ ]")
            step_lines.append(f"  {marker} Step {step.index}: {step.title}")
        parts.append(ACTIVE_PLAN_TEMPLATE.format(
            objective=plan.objective,
            status=plan.status,
            steps="\n".join(step_lines),
        ))

    # 5. Todo list
    if todos:
        todo_lines = []
        markers = {"pending": "○", "in_progress": "◐", "completed": "●"}
        for todo in todos:
            marker = markers.get(todo.get("status", "pending"), "○")
            content = todo.get("content", "")
            todo_lines.append(f"  {marker} {content}")
        parts.append(TODO_CONTEXT_TEMPLATE.format(todo_list="\n".join(todo_lines)))

    # 6. Project context (injected as XML <context> tags, matching Kode-Agent)
    if project_context:
        # Filter out projectDocs from inline context (too large);
        # instruction note is kept as a separate reminder.
        filtered = {
            k: v for k, v in project_context.items()
            if k not in ("projectDocs",)
        }
        if filtered:
            parts.append(
                "\nAs you answer the user's questions, "
                "you can use the following context:\n"
            )
            for key, value in filtered.items():
                parts.append(f'<context name="{key}">{value}</context>')

    # 7. System reminders (mention-derived, instruction file notes, etc.)
    if system_reminders:
        for reminder in system_reminders:
            if reminder:
                parts.append(f"\n{reminder}")

    return "".join(parts)
