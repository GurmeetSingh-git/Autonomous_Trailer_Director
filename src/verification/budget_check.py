"""Verify runtime and production budget constraints."""


def check(candidate, context=None) -> bool:
    """Return whether the candidate fits its budget."""
    limit = (context or {}).get("max_cost_usd", float("inf"))
    return (context or {}).get("estimated_cost_usd", 0.0) <= limit
