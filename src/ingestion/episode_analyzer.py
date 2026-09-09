"""Parse an episode package into raw scene records."""

from typing import Any


class EpisodeAnalyzer:
    """Extract raw scene records from an episode package."""

    def analyze(self, episode_package: Any) -> list[dict[str, Any]]:
        """Return raw scene records for an episode package."""
        raise NotImplementedError
