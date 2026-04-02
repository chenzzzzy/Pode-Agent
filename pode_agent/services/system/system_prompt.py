"""System prompt assembly for the Agentic Loop.

Phase 2: minimal system prompt with base personality + CWD info.
Dynamic context, plan mode, and reminders are deferred to later phases.

Reference: docs/agent-loop.md — System Prompt
"""

from __future__ import annotations

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
"""


def build_system_prompt(base: str, cwd: str) -> str:
    """Assemble the full system prompt.

    Phase 2: base prompt + CWD info only.
    """
    parts = [base]
    if cwd:
        parts.append(CWD_TEMPLATE.format(cwd=cwd))
    return "".join(parts)
