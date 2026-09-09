"""Verify asset and clip rights."""


def check(candidate, context=None) -> dict:
    """Return rights severity and an auditable explanation."""
    cleared = (context or {}).get("cleared_scene_ids")
    if not cleared:
        return {"status": "warning", "detail": "Contract clearance was not supplied; human approval is required."}
    if all(item.get("scene_id") in cleared for item in candidate):
        return {"status": "pass", "detail": "All selected scene assets are cleared."}
    return {"status": "fail", "detail": "At least one selected scene is not contract-cleared."}
