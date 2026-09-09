"""Select candidate scenes for an audience strategy."""

from typing import Any


class CandidateSelector:
    """Propose scenes and ordering for an audience promise."""

    def select(self, audience_promise: dict[str, Any], scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return ordered candidate scene records."""
        return [scene for scene in scenes if scene.get("selected", True) and scene.get("spoiler_level", "low") != "high"][:3]


def generate_candidates(audience: str, story_map: dict[str, Any], audience_promise: str) -> list[dict[str, Any]]:
    """Return a small, deterministic candidate set for the graph and CLI."""
    del audience, audience_promise
    return CandidateSelector().select({}, story_map.get("scenes", []))
