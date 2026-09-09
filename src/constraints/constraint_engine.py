"""Apply policies and contracts to a story map."""

from typing import Any

from models.constraint_map import ConstraintMap
from models.story_map import StoryMap


class ConstraintEngine:
    """Build constraints that govern trailer planning."""

    def build(self, story_map: StoryMap, policies: list[dict[str, Any]] | None = None) -> ConstraintMap:
        """Create a constraint map from policies and contracts."""
        raise NotImplementedError
