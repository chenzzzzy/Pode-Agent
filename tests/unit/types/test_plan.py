"""Unit tests for Plan data models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pode_agent.types.plan import Plan, PlanStep, PlanStatus, StepStatus


class TestPlanStep:
    """Tests for PlanStep model."""

    def test_defaults(self) -> None:
        step = PlanStep(index=1, title="Read codebase")
        assert step.index == 1
        assert step.title == "Read codebase"
        assert step.description == ""
        assert step.tools == []
        assert step.status == StepStatus.PENDING
        assert step.result_summary is None

    def test_full_construction(self) -> None:
        step = PlanStep(
            index=3,
            title="Run tests",
            description="Execute pytest suite",
            tools=["bash"],
            status=StepStatus.RUNNING,
            result_summary="All passed",
        )
        assert step.index == 3
        assert step.tools == ["bash"]
        assert step.status == StepStatus.RUNNING

    def test_serialization_roundtrip(self) -> None:
        step = PlanStep(index=1, title="Step", status=StepStatus.DONE)
        data = step.model_dump()
        restored = PlanStep.model_validate(data)
        assert restored == step


class TestPlan:
    """Tests for Plan model."""

    def test_defaults(self) -> None:
        plan = Plan(objective="Refactor auth module")
        assert plan.plan_id  # UUID generated
        assert plan.status == PlanStatus.DRAFT
        assert plan.steps == []
        assert plan.acceptance_criteria == []
        assert plan.risks == []
        assert plan.rollback_plan is None

    def test_full_construction(self) -> None:
        plan = Plan(
            objective="Fix login bug",
            steps=[
                PlanStep(index=1, title="Investigate"),
                PlanStep(index=2, title="Fix"),
            ],
            acceptance_criteria=["Login works with valid creds"],
            risks=["May break signup flow"],
            rollback_plan="Revert commit",
            status=PlanStatus.APPROVED,
        )
        assert len(plan.steps) == 2
        assert plan.status == PlanStatus.APPROVED
        assert "Login works" in plan.acceptance_criteria[0]

    def test_plan_id_is_valid_uuid(self) -> None:
        plan = Plan(objective="Test")
        parsed = uuid.UUID(plan.plan_id)
        assert str(parsed) == plan.plan_id

    def test_timestamps_are_utc(self) -> None:
        plan = Plan(objective="Test")
        assert plan.created_at.tzinfo == timezone.utc
        assert plan.updated_at.tzinfo == timezone.utc

    def test_serialization_roundtrip(self) -> None:
        plan = Plan(
            objective="Refactor",
            steps=[PlanStep(index=1, title="A"), PlanStep(index=2, title="B")],
        )
        data = plan.model_dump()
        restored = Plan.model_validate(data)
        assert restored.objective == plan.objective
        assert len(restored.steps) == 2

    def test_json_roundtrip(self) -> None:
        plan = Plan(objective="JSON test")
        json_str = plan.model_dump_json()
        restored = Plan.model_validate_json(json_str)
        assert restored.objective == "JSON test"


class TestEnums:
    """Tests for StepStatus and PlanStatus enums."""

    def test_step_status_values(self) -> None:
        assert StepStatus.PENDING == "pending"
        assert StepStatus.RUNNING == "running"
        assert StepStatus.DONE == "done"
        assert StepStatus.SKIPPED == "skipped"
        assert StepStatus.FAILED == "failed"

    def test_plan_status_values(self) -> None:
        assert PlanStatus.DRAFT == "draft"
        assert PlanStatus.APPROVED == "approved"
        assert PlanStatus.EXECUTING == "executing"
        assert PlanStatus.DONE == "done"
        assert PlanStatus.CANCELLED == "cancelled"
