"""AskExpertModelTool: delegate complex tasks to a more capable AI model.

Allows the agent to consult a stronger model for difficult reasoning,
code review, or architectural decisions.  Phase 3 skeleton returns a
placeholder since the full wiring depends on query.py integration.

Reference: docs/api-specs.md -- Tool System API, AskExpertModelTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class AskExpertInput(BaseModel):
    """Input schema for AskExpertModelTool."""

    prompt: str = Field(description="The question or task to send to the expert model")
    model: str | None = Field(
        default=None,
        description="Specific model to use (defaults to the configured expert model)",
    )
    context: str | None = Field(
        default=None,
        description="Additional context to include with the prompt",
    )


class AskExpertModelTool(Tool):
    """Ask a more capable AI model for help with complex tasks.

    Phase 3 skeleton: the full wiring depends on query.py integration,
    so this tool currently returns a placeholder response.
    """

    name: str = "ask_expert_model"
    description: str = (
        "Ask a more capable AI model for help with complex tasks. "
        "Use this for difficult reasoning, code review, or architectural decisions."
    )

    def input_schema(self) -> type[BaseModel]:
        return AskExpertInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, AskExpertInput)

        # Phase 3 skeleton: expert model not yet wired up
        yield ToolOutput(
            type="result",
            data={
                "error": "Expert model not yet configured",
                "prompt": input.prompt,
            },
            result_for_assistant=(
                "Expert model is not yet configured. "
                "Proceed with available context and reasoning."
            ),
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
