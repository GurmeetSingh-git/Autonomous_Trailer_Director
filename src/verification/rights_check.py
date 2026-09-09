"""Verify asset and clip rights."""


def check(candidate, context=None) -> bool:
    """Return whether candidate assets are cleared for use."""
    cleared = (context or {}).get("cleared_scene_ids")
    return cleared is None or all(item.get("scene_id") in cleared for item in candidate)
