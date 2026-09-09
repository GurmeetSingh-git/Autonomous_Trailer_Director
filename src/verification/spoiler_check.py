"""Verify spoiler policy compliance."""


def check(candidate, context=None) -> bool:
    """Return whether the candidate avoids prohibited spoilers."""
    del context
    return all(item.get("spoiler_level", "low") != "high" for item in candidate)
