"""Verify rating and content policy compliance."""


def check(candidate, context=None) -> bool:
    """Return whether the candidate meets rating constraints."""
    audience = (context or {}).get("audience", "family")
    return audience != "family" or all(item.get("sensitive_content", []) == [] for item in candidate)
