"""Plan mode data models.

Defines the data structures for plan-based agentic workflows:
- Plans contain ordered steps with acceptance criteria and risk assessments
- Steps track individual task progress through status lifecycle
- Plans transition through draft → approved → executing → done/cancelled

Reference: docs/plan-mode.md — Plan Data Model
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class StepStatus(StrEnum):
    """Status of a single plan step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class PlanStatus(StrEnum):
    """Overall status of a plan."""

    DRAFT = "draft"
    APPROVED = "approved"
    EXECUTING = "executing"
    DONE = "done"
    CANCELLED = "cancelled"


class PlanStep(BaseModel):
    """A single step within a plan."""

    index: int = Field(description="1-based step number")
    title: str = Field(description="Short title of the step")
    description: str = Field(default="", description="Detailed description")
    tools: list[str] = Field(default_factory=list, description="Advisory tool names")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Current status")
    result_summary: str | None = Field(default=None, description="Summary after completion")


class Plan(BaseModel):
    """A structured execution plan produced in plan mode."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    slug: str | None = Field(default=None, description="Human-readable identifier")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Creation timestamp",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last update timestamp",
    )
    objective: str = Field(description="What the plan aims to achieve")
    research_notes: str | None = Field(default=None, description="Notes from exploration")
    steps: list[PlanStep] = Field(default_factory=list, description="Ordered steps")
    acceptance_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rollback_plan: str | None = Field(default=None)
    test_matrix: str | None = Field(default=None)
    status: PlanStatus = Field(default=PlanStatus.DRAFT)

    model_config = {}
