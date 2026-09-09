"""Track model calls and cost for a run."""


class BudgetTracker:
    """Meter calls against a configured run budget."""

    def record(self, cost: float) -> None:
        """Record an incurred cost."""
        raise NotImplementedError

    def remaining(self) -> float:
        """Return the remaining budget."""
        raise NotImplementedError
