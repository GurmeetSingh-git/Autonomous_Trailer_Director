"""Verify runtime and production budget constraints."""


def check(candidate, context=None) -> dict:
    """Return budget severity and an auditable explanation."""
    del candidate
    limit = (context or {}).get("max_cost_usd", float("inf"))
    estimate = (context or {}).get("estimated_cost_usd", 0.0)
    if estimate <= limit:
        return {"status": "pass", "detail": f"Estimated cost ${estimate:.2f} is within the ${limit:.2f} budget."}
    return {"status": "fail", "detail": f"Estimated cost ${estimate:.2f} exceeds the ${limit:.2f} budget."}
