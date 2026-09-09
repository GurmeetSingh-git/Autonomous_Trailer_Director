"""Apply policies and contracts to a story map."""

from typing import Any

from src.models.constraint_map import ConstraintMap
from src.models.story_map import StoryMap


class ConstraintEngine:
    """Build constraints that govern trailer planning."""

    def build(self, story_map: StoryMap, policies: list[dict[str, Any]] | None = None) -> ConstraintMap:
        """Create a constraint map from policies and contracts."""
        default_policies = [
            {"id": "no_major_spoilers", "rule": "exclude high-risk scenes"},
            {"id": "source_accuracy", "rule": "scene ids and timecodes must exist"},
            {"id": "audience_safety", "rule": "exclude sensitive content for family"},
        ]
        return ConstraintMap(
            policies=policies or default_policies,
            metadata={"scene_ids": [scene.get("id") for scene in story_map.scenes]},
        )
