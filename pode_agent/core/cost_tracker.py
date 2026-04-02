"""Module-level cost tracking for API usage.

Tracks cumulative USD cost across all LLM API calls within a session.

Reference: docs/api-specs.md — Cost Tracker API
"""

from __future__ import annotations

from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_total_cost_usd: float = 0.0


def add_to_total_cost(cost_usd: float) -> None:
    """Add a cost amount to the running total."""
    global _total_cost_usd  # noqa: PLW0603
    _total_cost_usd += cost_usd
    logger.debug("Cost added: $%.6f (total: $%.6f)", cost_usd, _total_cost_usd)


def get_total_cost() -> float:
    """Return the cumulative cost in USD."""
    return _total_cost_usd


def reset_cost() -> None:
    """Reset the cumulative cost to zero."""
    global _total_cost_usd  # noqa: PLW0603
    _total_cost_usd = 0.0


# ---------------------------------------------------------------------------
# Price table (USD per 1M tokens)
# ---------------------------------------------------------------------------

# Format: (input_per_m, output_per_m)
_MODEL_PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-sonnet-4-5-20251101": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-opus-4": (15.0, 75.0),
    # OpenAI
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "o1": (15.0, 60.0),
    "o1-mini": (3.0, 12.0),
}


def calculate_model_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate USD cost for a given model and token usage.

    Returns 0.0 for unknown models.
    """
    prices = _MODEL_PRICES.get(model)
    if prices is None:
        # Try prefix match for versioned model names
        for key, prices in _MODEL_PRICES.items():  # noqa: B007
            if model.startswith(key):
                break
        else:
            return 0.0

    input_per_token = prices[0] / 1_000_000
    output_per_token = prices[1] / 1_000_000
    return input_tokens * input_per_token + output_tokens * output_per_token
