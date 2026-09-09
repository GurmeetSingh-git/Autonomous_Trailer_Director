"""Select candidate scenes for an audience strategy."""

from typing import Any


class CandidateSelector:
    """Propose scenes and ordering for an audience promise."""

    def select(self, audience_promise: dict[str, Any], scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return ordered candidate scene records."""
        raise NotImplementedError
