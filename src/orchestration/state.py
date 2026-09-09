# src/orchestration/state.py
from typing import TypedDict, Literal


class TrailerState(TypedDict):
    audience: str
    story_map: dict
    constraint_map: dict
    audience_promise: str
    segments: list[dict]          # current candidate/validated segments
    validation: dict              # {"status": ..., "failures": [...]}
    repair_attempts: int
    status: Literal["planning", "validating", "repairing", "done", "rejected"]
    decision_log: list[dict]
    final_edl: dict | None