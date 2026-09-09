"""Verify referenced assets and scenes exist."""


def check(candidate, context=None) -> bool:
    """Return whether all candidate references exist."""
    scene_ids = set((context or {}).get("scene_ids", []))
    return all(item.get("scene_id") in scene_ids for item in candidate)
