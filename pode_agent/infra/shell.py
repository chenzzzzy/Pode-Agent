"""Shell command execution base.

Provides an async wrapper around ``asyncio.create_subprocess_exec``
with timeout and abort support.

Reference: docs/architecture.md — Async model, Shell executor
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ShellResult:
    """Result of a shell command execution."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


async def execute_shell(
    command: str,
    timeout: float | None = 120.0,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    abort_event: asyncio.Event | None = None,
) -> ShellResult:
    """Execute a shell command asynchronously.

    .. warning::

        This function uses ``/bin/sh -c`` (or ``cmd /c`` on Windows)
        to execute the command string. Callers **must not** pass
        unsanitized user or LLM-generated input directly — that would
        allow command injection. Use :func:`execute_command` for
        safe, argument-based invocation instead.

    Args:
        command: Shell command string.
        timeout: Maximum execution time in seconds. None = no timeout.
        cwd: Working directory for the command.
        env: Extra environment variables (merged with current env).
        abort_event: If set, the process is killed.

    Returns:
        ShellResult with captured stdout, stderr, and exit code.
    """
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    return await _wait_for_process(proc, timeout, abort_event)


async def execute_command(
    args: list[str],
    timeout: float | None = 120.0,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    abort_event: asyncio.Event | None = None,
) -> ShellResult:
    """Execute a command safely using ``exec`` (no shell interpolation).

    This is the **preferred** way to run commands because it avoids
    shell injection vulnerabilities. Each element of *args* is passed
    directly as a separate argument.

    Args:
        args: Command and arguments, e.g. ``["git", "status"]``.
        timeout: Maximum execution time in seconds. None = no timeout.
        cwd: Working directory for the command.
        env: Extra environment variables (merged with current env).
        abort_event: If set, the process is killed.

    Returns:
        ShellResult with captured stdout, stderr, and exit code.
    """
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    return await _wait_for_process(proc, timeout, abort_event)


async def _wait_for_process(
    proc: asyncio.subprocess.Process,
    timeout: float | None,
    abort_event: asyncio.Event | None,
) -> ShellResult:
    """Wait for a subprocess to complete, with timeout and abort support."""
    try:
        if abort_event is not None:
            comm_task = asyncio.create_task(proc.communicate())
            abort_task = asyncio.create_task(abort_event.wait())

            done, pending = await asyncio.wait(
                [comm_task, abort_task],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()

            if abort_task in done:
                # abort_event was set — kill the process
                proc.kill()
                await proc.wait()
                return ShellResult(
                    stdout="",
                    stderr="Aborted by user",
                    exit_code=-1,
                )

            if comm_task not in done:
                # Timeout — neither task completed
                raise TimeoutError

            # Process completed — get result from the communicate task
            stdout_bytes, stderr_bytes = comm_task.result()
        else:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

    except TimeoutError:
        proc.kill()
        await proc.wait()
        return ShellResult(
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            exit_code=-1,
            timed_out=True,
        )

    return ShellResult(
        stdout=(stdout_bytes or b"").decode(errors="replace"),
        stderr=(stderr_bytes or b"").decode(errors="replace"),
        exit_code=proc.returncode if proc.returncode is not None else -1,
    )
