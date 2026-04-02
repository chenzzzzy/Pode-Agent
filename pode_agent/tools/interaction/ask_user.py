"""AskUserQuestionTool: prompt the user for input during agent execution.

In interactive (TUI) mode the question is displayed and the user's response
is fed back into the conversation.  In non-interactive (print / headless)
mode the tool yields an error because no user is available to answer.

Reference: docs/api-specs.md -- Tool System API, AskUserQuestionTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class AskUserInput(BaseModel):
    """Input schema for AskUserQuestionTool."""

    question: str = Field(description="The question to ask the user")
    options: list[str] | None = Field(
        default=None,
        description="Optional list of choices for the user to pick from",
    )


class AskUserQuestionTool(Tool):
    """Ask the user a question during agent execution.

    The question is forwarded to the UI layer so the human operator can
    respond.  When running in non-interactive / headless mode the tool
    returns an error message instead.
    """

    name: str = "ask_user_question"
    description: str = (
        "Ask the user a question during agent execution and wait for their response. "
        "Use this when you need clarification or a decision from the user."
    )

    def input_schema(self) -> type[BaseModel]:
        return AskUserInput

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
        assert isinstance(input, AskUserInput)

        # Non-interactive mode -- no session / abort_event available
        if context.abort_event is None:
            yield ToolOutput(
                type="result",
                data={"error": "Interactive mode required to ask user questions"},
                result_for_assistant=(
                    "Error: Cannot ask the user a question in non-interactive mode. "
                    "Please use available context to proceed without user input."
                ),
            )
            return

        # Format the question (with optional choices) for the LLM
        question_text = input.question
        if input.options:
            options_text = ", ".join(input.options)
            question_text = f"{input.question}\nOptions: [{options_text}]"

        yield ToolOutput(
            type="result",
            data={"question": input.question, "options": input.options},
            result_for_assistant=question_text,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
