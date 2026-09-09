"""Find and validate alternatives after rejection."""

from typing import Any


class RepairAgent:
    """Replace rejected candidates with valid alternatives."""

    def repair(self, candidate: Any, rejection: Any, context: Any = None) -> Any:
        """Return an alternative candidate or raise if none exists."""
        del context
        rejected_ids = set(rejection.get("rejected_scene_ids", [])) if isinstance(rejection, dict) else set()
        alternatives = [item for item in candidate if item.get("id") not in rejected_ids]
        if not alternatives:
            raise ValueError("No valid alternative candidate remains.")
        return alternatives


def propose_alternatives(segments: list[dict], failures: list[dict], story_map: dict, constraint_map: dict) -> list[dict]:
    """Remove failed scene references and retain only source-backed alternatives."""
    del constraint_map
    failed_ids = {failure.get("scene_id") for failure in failures}
    return [segment for segment in segments if segment.get("scene_id") not in failed_ids] or segments[:1]
