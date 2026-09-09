"""Verify bias and representation constraints."""


def check(candidate, context=None) -> bool:
    """Return whether the candidate meets bias constraints."""
    return not any("stereotype" in str(item).lower() for item in candidate)
