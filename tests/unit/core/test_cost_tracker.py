"""Tests for core/cost_tracker.py — API cost tracking."""

from __future__ import annotations

from pode_agent.core import cost_tracker


class TestCostTracker:
    def setup_method(self) -> None:
        """Reset cost before each test."""
        cost_tracker.reset_cost()

    def test_initial_cost_is_zero(self) -> None:
        assert cost_tracker.get_total_cost() == 0.0

    def test_add_cost(self) -> None:
        cost_tracker.add_to_total_cost(0.005)
        assert cost_tracker.get_total_cost() == pytest.approx(0.005)

    def test_accumulates(self) -> None:
        cost_tracker.add_to_total_cost(0.003)
        cost_tracker.add_to_total_cost(0.002)
        assert cost_tracker.get_total_cost() == pytest.approx(0.005)

    def test_reset(self) -> None:
        cost_tracker.add_to_total_cost(1.0)
        cost_tracker.reset_cost()
        assert cost_tracker.get_total_cost() == 0.0

    def test_calculate_known_model(self) -> None:
        # claude-sonnet-4-5: $3/million input, $15/million output
        cost = cost_tracker.calculate_model_cost("claude-sonnet-4-5-20251101", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_calculate_prefix_match(self) -> None:
        # Should match "gpt-4o" prefix
        cost = cost_tracker.calculate_model_cost("gpt-4o-2024-08-06", 1000, 500)
        expected = (1000 * 2.50 + 500 * 10.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_calculate_unknown_model(self) -> None:
        cost = cost_tracker.calculate_model_cost("unknown-model-xyz", 1000, 500)
        assert cost == 0.0


import pytest  # noqa: E402 — needed at top but pytest.approx used above
