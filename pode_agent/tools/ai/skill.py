"""SkillTool: execute a registered skill (plugin).

Skills are named, reusable procedures that can be installed and invoked
by the LLM. This tool discovers, lists, and invokes skills by loading
their prompt content from SKILL.md files.

Reference: docs/skill-system.md — SkillTool 设计
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger
from pode_agent.services.plugins.commands import load_custom_commands
from pode_agent.types.skill import ContextModifier

logger = get_logger(__name__)

# Character budget for skill listing in tool description
_CHAR_BUDGET = int(os.environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET", "15000"))


class SkillInput(BaseModel):
    """Input schema for SkillTool.

    Reference: docs/skill-system.md — SkillInput
    """

    skill: str = Field(
        description="Name of the skill to invoke",
    )
    args: str | None = Field(
        default=None,
        description="Arguments to pass to the skill",
    )


class SkillTool(Tool):
    """Execute a registered skill.

    Skills are named, reusable procedures that extend the agent's
    capabilities via Markdown prompt templates. The LLM discovers
    available skills via the dynamic description and invokes them
    by name.

    Reference: docs/skill-system.md — SkillTool 完整实现规格
    """

    name: str = "skill"
    description: str = "Execute a registered skill"

    def input_schema(self) -> type[BaseModel]:
        return SkillInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, SkillInput)

        # 1. Load all custom commands/skills
        commands = await load_custom_commands()

        # 2. Find matching skill by name
        cmd = next(
            (c for c in commands if c.name == input.skill and c.is_skill),
            None,
        )
        if cmd is None:
            yield ToolOutput(
                type="result",
                data={"error": f"Skill not found: {input.skill}"},
                result_for_assistant=f"Skill not found: {input.skill}",
            )
            return

        # 3. Generate prompt with $ARGUMENTS substitution
        prompt_text = cmd.get_prompt_for_command(input.args)

        # 4. Build context modifier from frontmatter
        context_modifier = self._build_context_modifier(cmd)

        # 5. Return result with new_messages and context_modifier
        result_text = f"Launching skill: {cmd.name}"
        yield ToolOutput(
            type="result",
            data={"success": True, "command_name": cmd.name},
            result_for_assistant=result_text,
            new_messages=[
                {"role": "user", "content": prompt_text},
            ],
            context_modifier=context_modifier,
        )

    def _build_context_modifier(
        self, cmd: Any,
    ) -> ContextModifier | None:
        """Extract ContextModifier from command's frontmatter.

        Reference: docs/skill-system.md — contextModifier 机制
        """
        fm = cmd.frontmatter
        if fm is None:
            return None
        if not any([fm.allowed_tools, fm.model, fm.max_thinking_tokens]):
            return None
        return ContextModifier(
            allowed_tools=fm.allowed_tools,
            model=fm.model,
            max_thinking_tokens=fm.max_thinking_tokens,
        )

    async def prompt(self) -> str:
        """Generate the skill listing description for the LLM.

        Respects character budget from SLASH_COMMAND_TOOL_CHAR_BUDGET env var.

        Reference: docs/skill-system.md — SkillTool.prompt()
        """
        commands = await load_custom_commands()
        skills = [
            c for c in commands
            if c.is_skill and c.frontmatter
            and not c.frontmatter.disable_model_invocation
        ]

        parts: list[str] = []
        used = 0

        for skill in skills:
            block = self._format_skill_block(skill)
            used += len(block) + 1
            if used > _CHAR_BUDGET:
                break
            parts.append(block)

        if not parts:
            return "No skills are currently installed."

        return "\n".join(parts)

    def _format_skill_block(self, cmd: Any) -> str:
        """Format a single skill's description block.

        Reference: docs/skill-system.md — _format_skill_block
        """
        fm = cmd.frontmatter
        lines = [f"- {cmd.name}: {fm.description}"]
        if fm.when_to_use:
            lines.append(f"  When to use: {fm.when_to_use}")
        if fm.argument_hint:
            lines.append(f"  Arguments: {fm.argument_hint}")
        return "\n".join(lines)

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
