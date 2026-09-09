"""Re-run only planning steps affected by an event."""

from typing import Any


class Replanner:
    """Replan affected portions of an active run."""

    def replan(self, event: Any, run_state: Any) -> Any:
        """Return updated planning results."""
        raise NotImplementedError
