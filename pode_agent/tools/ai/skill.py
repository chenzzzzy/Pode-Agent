"""SkillTool: execute a registered skill (plugin).

Skills are named, reusable procedures that can be installed and invoked
by the agent.  Phase 3 skeleton returns an error since no skills are
installed yet.

Reference: docs/api-specs.md -- Tool System API, SkillTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class SkillInput(BaseModel):
    """Input schema for SkillTool."""

    skill_name: str = Field(description="Name of the skill to execute")
    args: dict[str, Any] | None = Field(
        default=None,
        description="Arguments to pass to the skill",
    )


class SkillTool(Tool):
    """Execute a registered skill (plugin).

    Phase 3 skeleton: no skills are installed yet.
    """

    name: str = "skill"
    description: str = (
        "Execute a registered skill (plugin). "
        "Skills are named, reusable procedures that extend the agent's capabilities."
    )

    def input_schema(self) -> type[BaseModel]:
        return SkillInput

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
        assert isinstance(input, SkillInput)

        # Phase 3 skeleton: no skills installed
        yield ToolOutput(
            type="result",
            data={
                "error": f"No skill found: {input.skill_name}",
                "skill_name": input.skill_name,
            },
            result_for_assistant=(
                f"No skills are currently installed. "
                f"Cannot execute skill: {input.skill_name}"
            ),
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
