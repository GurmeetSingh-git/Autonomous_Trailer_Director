"""Choose an audience promise before selecting clips."""

from typing import Any


class AudienceStrategist:
    """Commit to the trailer's audience promise."""

    def commit(self, audience: str, story_context: Any) -> dict[str, Any]:
        """Return an audience promise and supporting strategy."""
        raise NotImplementedError
