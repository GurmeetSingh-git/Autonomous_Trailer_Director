"""Track dependencies between assets, scenes, constraints, and segments."""

from typing import Any


class DependencyGraph:
    """Resolve segments affected by a changed dependency."""

    def affected_segments(self, dependency: str) -> list[str]:
        """Return segment identifiers affected by a dependency."""
        raise NotImplementedError
