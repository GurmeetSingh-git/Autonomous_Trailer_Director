"""LangGraph workflow for human trailer review and regeneration."""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

from src.logging.decision_log import DecisionLog
from src.orchestration.pipeline import build_plan
from src.verification.validator import Validator


class ReviewState(TypedDict):
    audience: str
    story_map: dict[str, Any]
    constraint_map: dict[str, Any]
    audience_promise: str
    feedback: str
    plan: dict[str, Any]
    validation: dict[str, Any]
    review_status: Literal["PENDING", "PASSED", "NEEDS_REVISION"]


def _validate(plan: dict[str, Any], state: ReviewState) -> dict[str, Any]:
    metadata = state["constraint_map"].get("metadata", {})
    return Validator().validate(
        plan["segments"],
        {
            "scene_ids": metadata.get("scene_ids", []),
            "cleared_scene_ids": metadata.get("cleared_scene_ids", []),
            "expired_assets": metadata.get("expired_assets", []),
            "protected_facts": metadata.get("protected_facts", []),
            "audience": state["audience"],
            "estimated_cost_usd": 0.02,
            "max_cost_usd": metadata.get("max_cost_usd", 1.0),
        },
    )


def _regenerate(state: ReviewState) -> ReviewState:
    plan = build_plan(state["audience"], state["story_map"], state["constraint_map"], DecisionLog())
    feedback = state["feedback"].strip()
    if feedback:
        for segment in plan["segments"]:
            segment["evidence"] = [*segment.get("evidence", []), "human:review_feedback"]
            segment["reason"] = f"{segment.get('reason', '')} Reviewer feedback: {feedback}"
    plan["validation"] = _validate(plan, state)
    return {**state, "plan": plan, "validation": plan["validation"], "review_status": "PENDING"}


def _build_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("regenerate", _regenerate)
    graph.set_entry_point("regenerate")
    graph.add_edge("regenerate", END)
    return graph.compile()


def regenerate_review(state: ReviewState) -> ReviewState:
    """Run one feedback-driven regeneration and validation pass."""
    return _build_graph().invoke(state)
