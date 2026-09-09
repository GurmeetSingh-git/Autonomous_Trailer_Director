"""Detect surprise events and mid-run changes."""

from typing import Any


class ChangeWatcher:
    """Detect changes that may invalidate a run."""

    def detect(self, previous_state: Any, current_state: Any) -> list[dict[str, Any]]:
        """Return detected changes."""
        raise NotImplementedError
