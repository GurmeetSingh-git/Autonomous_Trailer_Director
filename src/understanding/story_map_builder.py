"""Build a structured story map from scenes and dialogue."""

from typing import Any

from models.story_map import StoryMap


class StoryMapBuilder:
    """Convert raw scenes and dialogue into a story map."""

    def build(self, raw_scenes: list[dict[str, Any]], dialogue: str = "") -> StoryMap:
        """Build a story map from raw scene records and dialogue."""
        raise NotImplementedError
