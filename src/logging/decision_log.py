"""Append-only decision and evidence log."""

from typing import Any


class DecisionLog:
    """Record structured decisions and supporting evidence."""

    def append(self, decision: str, evidence: dict[str, Any]) -> None:
        """Append one decision record."""
        raise NotImplementedError
