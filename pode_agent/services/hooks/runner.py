"""Hook runner — executes hooks at each injection point.

Loads hook configurations from settings, matches by event type and tool
name glob, executes command or prompt hooks, and aggregates results.

Command hooks receive a JSON payload on stdin and must write a JSON
result to stdout within ``timeout_ms`` milliseconds.

Prompt hooks invoke the LLM with a specialised system prompt and parse
the structured response.

Reference: docs/hooks.md — Hook Execution Model
"""

from __future__ import annotations

import asyncio
import fnmatch
import json
from typing import Any, Literal

from pode_agent.infra.logging import get_logger
from pode_agent.services.hooks.base import (
    HookConfig,
    HookEvent,
    HookResult,
    HookState,
    PostToolUsePayload,
    PreToolUsePayload,
    StopPayload,
    UserPromptSubmitPayload,
)

logger = get_logger(__name__)

MAX_STOP_HOOK_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------


def load_hook_configs(
    project_settings: dict[str, Any] | None = None,
    user_settings: dict[str, Any] | None = None,
) -> list[HookConfig]:
    """Load and merge hook configurations from project and user settings.

    Both sources are optional; returns an empty list when no hooks are
    configured.
    """
    configs: list[HookConfig] = []
    for settings in (project_settings, user_settings):
        if not settings:
            continue
        hooks_raw = settings.get("hooks", [])
        for raw in hooks_raw:
            try:
                configs.append(HookConfig(**raw))
            except Exception:
                logger.warning("Skipping invalid hook config: %s", raw)
    return configs


def _matching_hooks(
    configs: list[HookConfig],
    event: HookEvent,
    tool_name: str | None = None,
) -> list[HookConfig]:
    """Filter hook configs by event type and optional tool name matcher."""
    matched: list[HookConfig] = []
    for cfg in configs:
        if cfg.event != event:
            continue
        if cfg.matcher == "all" or tool_name is not None and fnmatch.fnmatch(tool_name, cfg.matcher):
            matched.append(cfg)
    return matched


# ---------------------------------------------------------------------------
# Command hook execution
# ---------------------------------------------------------------------------


async def _execute_command_hook(
    config: HookConfig,
    payload: dict[str, Any],
) -> HookResult:
    """Run a command hook: spawn subprocess, send JSON on stdin, read stdout."""
    if not config.command:
        return HookResult(action="continue")

    try:
        proc = await asyncio.create_subprocess_exec(
            *config.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdin_data = json.dumps(payload).encode()
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=config.timeout_ms / 1000,
            )
        except TimeoutError:
            proc.kill()
            logger.warning("Hook timed out: %s", config.command)
            return HookResult(action="continue")

        if proc.returncode != 0:
            logger.warning(
                "Hook exited with code %d: %s", proc.returncode, stderr.decode()[:200]
            )
            return HookResult(action="continue")

        result_data = json.loads(stdout.decode())
        return HookResult(
            action=result_data.get("action", "continue"),
            message=result_data.get("message"),
            modified_data=result_data.get("modified_data"),
            additional_system_prompt=result_data.get("additional_system_prompt"),
            permission_decision=result_data.get("permission_decision"),
        )

    except Exception:
        logger.exception("Failed to execute hook: %s", config.command)
        return HookResult(action="continue")


# ---------------------------------------------------------------------------
# Prompt hook execution
# ---------------------------------------------------------------------------


async def _execute_prompt_hook(
    config: HookConfig,
    payload: dict[str, Any],
) -> HookResult:
    """Run a prompt hook: invoke LLM with structured prompt, parse response.

    Falls back to ``continue`` if the LLM call fails or returns invalid JSON.
    """
    if not config.prompt_text:
        return HookResult(action="continue")

    try:
        from pode_agent.services.ai.base import UnifiedRequestParams
        from pode_agent.services.ai.factory import query_llm

        prompt = (
            f"{config.prompt_text}\n\n"
            f"## Payload\n```json\n{json.dumps(payload, indent=2)}\n```\n\n"
            "Respond with a JSON object containing: action (continue|block|modify), "
            "message (optional), modified_data (optional), "
            "additional_system_prompt (optional), permission_decision (optional)."
        )

        params = UnifiedRequestParams(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a hook evaluator. Respond only with valid JSON.",
            model="claude-haiku-4-5",
            max_tokens=1024,
        )

        text_parts: list[str] = []
        async for resp in query_llm(params):
            if resp.type == "text_delta" and resp.text:
                text_parts.append(resp.text)

        full_text = "".join(text_parts)
        # Strip markdown code fences if present
        if full_text.strip().startswith("```"):
            lines = full_text.strip().split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            full_text = "\n".join(lines)

        result_data = json.loads(full_text)
        return HookResult(
            action=result_data.get("action", "continue"),
            message=result_data.get("message"),
            modified_data=result_data.get("modified_data"),
            additional_system_prompt=result_data.get("additional_system_prompt"),
            permission_decision=result_data.get("permission_decision"),
        )

    except Exception:
        logger.exception("Prompt hook failed")
        return HookResult(action="continue")


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------


def _aggregate_results(results: list[HookResult]) -> HookResult:
    """Aggregate multiple hook results into a single result.

    Priority: any ``block`` → block; any ``modify`` → modify; else continue.
    """
    if not results:
        return HookResult(action="continue")

    prompts: list[str] = []
    final_action: Literal["continue", "block", "modify"] = "continue"
    modified_data: Any = None
    message: str | None = None
    perm_decision: Literal["allow", "deny", "ask", "passthrough"] | None = None

    for r in results:
        if r.action == "block":
            final_action = "block"
            message = r.message or message
        elif r.action == "modify":
            if final_action != "block":
                final_action = "modify"
            modified_data = r.modified_data or modified_data
        if r.additional_system_prompt:
            prompts.append(r.additional_system_prompt)
        if r.permission_decision:
            perm_decision = r.permission_decision

    return HookResult(
        action=final_action,
        message=message,
        modified_data=modified_data,
        additional_system_prompt="\n\n".join(prompts) if prompts else None,
        permission_decision=perm_decision,
    )


# ---------------------------------------------------------------------------
# Public API — 4 injection point runners
# ---------------------------------------------------------------------------


async def run_user_prompt_submit_hooks(
    prompt: str,
    messages: list[dict[str, Any]],
    hook_state: HookState,
    configs: list[HookConfig] | None = None,
) -> HookResult:
    """Execute UserPromptSubmit hooks.

    Only runs once per query_core invocation (tracked in hook_state).
    """
    if hook_state.user_prompt_hooks_ran:
        return HookResult(action="continue")

    if not configs:
        return HookResult(action="continue")

    matched = _matching_hooks(configs, HookEvent.USER_PROMPT_SUBMIT)
    if not matched:
        return HookResult(action="continue")

    payload = UserPromptSubmitPayload(prompt=prompt, messages=messages)
    results: list[HookResult] = []

    for cfg in matched:
        if cfg.type == "command":
            r = await _execute_command_hook(cfg, payload.model_dump())
        else:
            r = await _execute_prompt_hook(cfg, payload.model_dump())
        results.append(r)

    hook_state.user_prompt_hooks_ran = True
    aggregated = _aggregate_results(results)

    if aggregated.additional_system_prompt:
        hook_state.additional_system_prompts.append(aggregated.additional_system_prompt)

    return aggregated


async def run_pre_tool_use_hooks(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_use_id: str,
    hook_state: HookState,
    configs: list[HookConfig] | None = None,
) -> HookResult:
    """Execute PreToolUse hooks. Can block or modify tool inputs."""
    if not configs:
        return HookResult(action="continue")

    matched = _matching_hooks(configs, HookEvent.PRE_TOOL_USE, tool_name)
    if not matched:
        return HookResult(action="continue")

    payload = PreToolUsePayload(
        tool_name=tool_name, tool_input=tool_input, tool_use_id=tool_use_id,
    )
    results: list[HookResult] = []

    for cfg in matched:
        if cfg.type == "command":
            r = await _execute_command_hook(cfg, payload.model_dump())
        else:
            r = await _execute_prompt_hook(cfg, payload.model_dump())
        results.append(r)

    return _aggregate_results(results)


async def run_post_tool_use_hooks(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_result: str,
    tool_use_id: str,
    is_error: bool,
    hook_state: HookState,
    configs: list[HookConfig] | None = None,
) -> HookResult:
    """Execute PostToolUse hooks. Can modify tool results."""
    if not configs:
        return HookResult(action="continue")

    matched = _matching_hooks(configs, HookEvent.POST_TOOL_USE, tool_name)
    if not matched:
        return HookResult(action="continue")

    payload = PostToolUsePayload(
        tool_name=tool_name,
        tool_input=tool_input,
        tool_result=tool_result,
        tool_use_id=tool_use_id,
        is_error=is_error,
    )
    results: list[HookResult] = []

    for cfg in matched:
        if cfg.type == "command":
            r = await _execute_command_hook(cfg, payload.model_dump())
        else:
            r = await _execute_prompt_hook(cfg, payload.model_dump())
        results.append(r)

    aggregated = _aggregate_results(results)

    if aggregated.additional_system_prompt:
        hook_state.additional_system_prompts.append(aggregated.additional_system_prompt)

    return aggregated


async def run_stop_hooks(
    messages: list[dict[str, Any]],
    stop_reason: str | None,
    hook_state: HookState,
    configs: list[HookConfig] | None = None,
) -> HookResult:
    """Execute Stop hooks. Can force the loop to continue."""
    if not configs:
        return HookResult(action="continue")

    matched = _matching_hooks(configs, HookEvent.STOP)
    if not matched:
        return HookResult(action="continue")

    payload = StopPayload(messages=messages, stop_reason=stop_reason)
    results: list[HookResult] = []

    for cfg in matched:
        if cfg.type == "command":
            r = await _execute_command_hook(cfg, payload.model_dump())
        else:
            r = await _execute_prompt_hook(cfg, payload.model_dump())
        results.append(r)

    aggregated = _aggregate_results(results)

    if aggregated.additional_system_prompt:
        hook_state.additional_system_prompts.append(aggregated.additional_system_prompt)

    return aggregated
