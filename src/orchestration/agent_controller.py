"""Drive the trailer director pipeline end to end."""

from typing import Any


class AgentController:
    """Coordinate ingestion, planning, verification, and repair."""

    def run(self, episode_package: Any, audience: str) -> Any:
        """Execute a trailer planning run."""
        raise NotImplementedError
