"""Orchestrate audience strategy and candidate selection."""

from typing import Any


class TrailerPlanner:
    """Coordinate strategy and candidate generation."""

    def plan(self, story_map: Any, constraint_map: Any, audience: str) -> list[dict[str, Any]]:
        """Return trailer candidates for the requested audience."""
        raise NotImplementedError
