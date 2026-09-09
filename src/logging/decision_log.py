"""Append-only decision and evidence log."""

from typing import Any


class DecisionLog:
    """Record structured decisions and supporting evidence."""

    def append(self, decision: str, evidence: dict[str, Any]) -> None:
        """Append one decision record."""
        self.records.append({"decision": decision, "evidence": evidence})

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def as_list(self) -> list[dict[str, Any]]:
        return list(self.records)


def log_event(event: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a graph-compatible structured decision event."""
    return {"event": event, "payload": payload}
