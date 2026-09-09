"""Find and validate alternatives after rejection."""

from typing import Any


class RepairAgent:
    """Replace rejected candidates with valid alternatives."""

    def repair(self, candidate: Any, rejection: Any, context: Any = None) -> Any:
        """Return an alternative candidate or raise if none exists."""
        raise NotImplementedError
