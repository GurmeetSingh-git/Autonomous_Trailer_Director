"""Verify accessibility requirements."""


def check(candidate, context=None) -> bool:
    """Return whether accessibility requirements are met."""
    return all(item.get("subtitle") and item.get("audio") for item in candidate)
