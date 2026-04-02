"""KillShellTool: terminate a background shell process.

Uses os.kill() on Unix or taskkill on Windows to send signals to
running processes by PID.

Reference: docs/api-specs.md -- Tool System API, KillShellTool
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Map signal names to values (Unix) — SIGKILL not available on Windows
_SIGNAL_MAP: dict[str, int] = {
    "SIGTERM": signal.SIGTERM,
    "SIGINT": signal.SIGINT,
}
if hasattr(signal, "SIGKILL"):
    _SIGNAL_MAP["SIGKILL"] = signal.SIGKILL


class KillShellInput(BaseModel):
    """Input schema for KillShellTool."""

    pid: int = Field(description="Process ID to terminate")
    signal: str = Field(default="SIGTERM", description="Signal to send (SIGTERM, SIGKILL, SIGINT)")


class KillShellTool(Tool):
    """Terminate a background shell process by PID."""

    name: str = "kill_shell"
    description: str = (
        "Terminate a background shell process by PID. "
        "Uses SIGTERM by default on Unix, taskkill on Windows."
    )

    def input_schema(self) -> type[BaseModel]:
        return KillShellInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, KillShellInput)

        if input.pid <= 0:
            yield ToolOutput(
                type="result",
                data={"error": f"Invalid PID: {input.pid}"},
                result_for_assistant=f"Error: Invalid PID: {input.pid}",
            )
            return

        sig_name = input.signal.upper()
        if sig_name not in _SIGNAL_MAP:
            valid = ", ".join(_SIGNAL_MAP.keys())
            yield ToolOutput(
                type="result",
                data={"error": f"Unsupported signal: {sig_name}. Valid signals: {valid}"},
                result_for_assistant=f"Error: Unsupported signal: {sig_name}. Valid signals: {valid}",
            )
            return

        if sys.platform == "win32":
            success, message = await self._kill_windows(input.pid, sig_name)
        else:
            success, message = self._kill_unix(input.pid, sig_name)

        if success:
            yield ToolOutput(
                type="result",
                data={
                    "pid": input.pid,
                    "signal": sig_name,
                    "message": message,
                },
                result_for_assistant=message,
            )
        else:
            yield ToolOutput(
                type="result",
                data={"error": message},
                result_for_assistant=f"Error: {message}",
            )

    @staticmethod
    def _kill_unix(pid: int, sig_name: str) -> tuple[bool, str]:
        """Send signal on Unix."""
        sig = _SIGNAL_MAP[sig_name]
        try:
            os.kill(pid, sig)
            return True, f"Sent {sig_name} to process {pid}"
        except ProcessLookupError:
            return False, f"Process {pid} not found"
        except PermissionError:
            return False, f"Permission denied to kill process {pid}"

    @staticmethod
    async def _kill_windows(pid: int, sig_name: str) -> tuple[bool, str]:
        """Send signal on Windows using taskkill."""
        force_flag = "/F" if sig_name in ("SIGKILL", "SIGTERM") else ""
        cmd = f"taskkill {force_flag} /PID {pid}".strip()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, f"Terminated process {pid}"
            err_msg = stderr.decode(errors="replace").strip() or f"Exit code {proc.returncode}"
            if "not found" in err_msg.lower() or "not found" in stdout.decode(errors="replace").lower():
                return False, f"Process {pid} not found"
            return False, f"Failed to kill process {pid}: {err_msg}"
        except Exception as exc:
            return False, f"Error killing process {pid}: {exc}"

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
