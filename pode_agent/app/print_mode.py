"""Print mode: single-query non-interactive execution.

Runs a single prompt through the Agentic Loop, prints the result,
and exits. Used for ``pode "prompt"`` CLI invocations.

Reference: docs/modules.md — Print Mode
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import BaseModel

from pode_agent.app.query import QueryOptions
from pode_agent.app.session import SessionManager
from pode_agent.core.permissions.types import PermissionMode
from pode_agent.core.tools.base import Tool
from pode_agent.types.session_events import SessionEventType


class PrintModeOptions(BaseModel):
    """Options for print mode execution."""

    model: str = "claude-sonnet-4-5-20251101"
    output_format: str = "text"  # "text" or "json"
    verbose: bool = False
    safe_mode: bool = False
    permission_mode: PermissionMode = PermissionMode.BYPASS_PERMISSIONS


async def run_print_mode(
    prompt: str,
    tools: list[Tool],
    options: PrintModeOptions,
) -> int:
    """Run a single query in print mode.

    Args:
        prompt: The user's prompt text.
        tools: Available tools.
        options: Print mode options.

    Returns:
        Exit code: 0=success, 1=error, 2=permission denied.
    """
    session = SessionManager(
        tools=tools,
        model=options.model,
    )

    query_opts = QueryOptions(
        model=options.model,
        permission_mode=options.permission_mode,
        verbose=options.verbose,
        safe_mode=options.safe_mode,
        cwd=str(Path.cwd()),
    )

    text_parts: list[str] = []
    exit_code = 0

    try:
        async for event in session.process_input(prompt, options=query_opts):
            if event.type == SessionEventType.ASSISTANT_DELTA and event.data:
                text = event.data.get("text", "")
                if text:
                    text_parts.append(text)
                    if options.output_format == "text":
                        sys.stdout.write(text)
                        sys.stdout.flush()

            elif event.type == SessionEventType.MODEL_ERROR:
                exit_code = 1
                if event.data:
                    sys.stderr.write(f"Error: {event.data.get('error', 'Unknown error')}\n")

            elif event.type == SessionEventType.TOOL_RESULT and event.data:
                if event.data.get("is_error") and options.verbose:
                        sys.stderr.write(
                            f"Tool error ({event.data.get('tool_name')}): "
                            f"{event.data.get('result')}\n"
                        )

            elif event.type == SessionEventType.PERMISSION_REQUEST:
                exit_code = 2
                sys.stderr.write("Permission denied in print mode.\n")
                break

    except KeyboardInterrupt:
        session.abort()
        exit_code = 130

    # Final output
    if options.output_format == "json":
        import json

        output = {
            "text": "".join(text_parts),
            "cost_usd": session.get_total_cost(),
            "model": options.model,
        }
        sys.stdout.write(json.dumps(output, indent=2) + "\n")
    elif options.output_format == "text" and text_parts:
        sys.stdout.write("\n")

    return exit_code
