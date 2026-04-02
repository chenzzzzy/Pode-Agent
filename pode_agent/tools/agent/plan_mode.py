"""EnterPlanModeTool and ExitPlanModeTool: plan-mode lifecycle management.

EnterPlanModeTool switches the agent into read-only exploration mode so it
can investigate the codebase without making changes.  ExitPlanModeTool
submits the resulting plan for approval and returns to normal execution.

Reference: docs/api-specs.md -- Tool System API, PlanModeTools
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class EnterPlanModeInput(BaseModel):
    """Input schema for EnterPlanModeTool."""

    objective: str = Field(description="What the agent aims to accomplish in plan mode")


class ExitPlanModeInput(BaseModel):
    """Input schema for ExitPlanModeTool."""

    objective: str = Field(description="Summary of the plan objective")
    steps: list[dict[str, Any]] = Field(
        description="Ordered list of plan steps (each step is a dict with title, description, etc.)",
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list,
        description="Criteria that must be met for the plan to be considered successful",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Potential risks or issues identified during planning",
    )


class EnterPlanModeTool(Tool):
    """Switch the agent into plan mode for read-only exploration."""

    name: str = "enter_plan_mode"
    description: str = (
        "Switch the agent into plan mode for read-only exploration. "
        "In plan mode, the agent investigates the codebase without making changes "
        "and produces a structured execution plan."
    )

    def input_schema(self) -> type[BaseModel]:
        return EnterPlanModeInput

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
        assert isinstance(input, EnterPlanModeInput)

        yield ToolOutput(
            type="result",
            data={
                "mode": "plan",
                "objective": input.objective,
            },
            result_for_assistant=(
                f"Switched to plan mode. Objective: {input.objective}\n"
                "The agent will now explore the codebase in read-only mode "
                "and produce a structured plan."
            ),
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)


class ExitPlanModeTool(Tool):
    """Exit plan mode and submit the plan for approval."""

    name: str = "exit_plan_mode"
    description: str = (
        "Exit plan mode and submit the plan for approval. "
        "The plan includes objective, steps, acceptance criteria, and risks."
    )

    def input_schema(self) -> type[BaseModel]:
        return ExitPlanModeInput

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
        assert isinstance(input, ExitPlanModeInput)

        plan_data: dict[str, Any] = {
            "objective": input.objective,
            "steps": input.steps,
            "acceptance_criteria": input.acceptance_criteria,
            "risks": input.risks,
        }

        # Format steps for readable output
        step_lines: list[str] = []
        for idx, step in enumerate(input.steps, 1):
            title = step.get("title", f"Step {idx}")
            step_lines.append(f"  {idx}. {title}")

        steps_text = "\n".join(step_lines) if step_lines else "  (no steps defined)"

        result_text = (
            f"Plan submitted for approval.\n\n"
            f"Objective: {input.objective}\n\n"
            f"Steps:\n{steps_text}\n"
        )

        if input.acceptance_criteria:
            criteria_lines = [f"  - {c}" for c in input.acceptance_criteria]
            result_text += "\nAcceptance Criteria:\n" + "\n".join(criteria_lines)

        if input.risks:
            risk_lines = [f"  - {r}" for r in input.risks]
            result_text += "\nRisks:\n" + "\n".join(risk_lines)

        yield ToolOutput(
            type="result",
            data={
                "event": "plan_created",
                "plan": plan_data,
            },
            result_for_assistant=result_text,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
