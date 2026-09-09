"""Verify untrusted content cannot alter pipeline instructions."""


def check(candidate, context=None) -> bool:
    """Return whether candidate content passes injection checks."""
    blocked = ("ignore previous", "ignore the contract", "reveal system prompt")
    return not any(token in str(candidate).lower() for token in blocked)
