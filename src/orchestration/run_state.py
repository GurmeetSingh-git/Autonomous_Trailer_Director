"""Per-run session state."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RunState:
    """Mutable state shared by one pipeline execution."""

    run_id: str
    values: dict[str, Any] = field(default_factory=dict)
