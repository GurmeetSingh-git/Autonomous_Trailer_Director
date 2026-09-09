# src/orchestration/agent_graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.orchestration.state import TrailerState
from src.planning.audience_strategy import build_audience_promise
from src.planning.candidate_selector import generate_candidates
from src.verification.validator import run_checks       # <- independent module
from src.repair.repair_agent import propose_alternatives
from src.models.edl import build_edl
from src.logging.decision_log import log_event

MAX_REPAIR_ATTEMPTS = 3


def node_plan_audience_strategy(state: TrailerState) -> TrailerState:
    state["audience_promise"] = build_audience_promise(state["audience"], state["story_map"])
    state["decision_log"].append(log_event("audience_strategy", {"promise": state["audience_promise"]}))
    return state


def node_generate_candidates(state: TrailerState) -> TrailerState:
    state["segments"] = generate_candidates(
        audience=state["audience"],
        story_map=state["story_map"],
        audience_promise=state["audience_promise"],
    )
    state["decision_log"].append(log_event("candidates_generated", {"segments": state["segments"]}))
    return state


def node_validate(state: TrailerState) -> TrailerState:
    # No access to the planner's prompt/context — only the proposed segments,
    # story_map, and constraint_map. Deterministic checks run first inside
    # run_checks(); only the fuzzy checks (spoiler/bias/accessibility) call
    # an LLM, with their own narrow system prompt.
    result = run_checks(
        segments=state["segments"],
        story_map=state["story_map"],
        constraint_map=state["constraint_map"],
        audience=state["audience"],
    )
    state["validation"] = result
    state["decision_log"].append(log_event("validation", result))
    return state


def node_repair(state: TrailerState) -> TrailerState:
    state["segments"] = propose_alternatives(
        segments=state["segments"],
        failures=state["validation"]["failures"],
        story_map=state["story_map"],
        constraint_map=state["constraint_map"],
    )
    state["repair_attempts"] += 1
    state["decision_log"].append(log_event("repair_attempt", {
        "attempt": state["repair_attempts"],
        "failures": state["validation"]["failures"],
    }))
    return state


def node_finalize(state: TrailerState) -> TrailerState:
    state["final_edl"] = build_edl(state)
    state["status"] = "done"
    state["decision_log"].append(log_event("finalized", {"status": state["validation"]["status"]}))
    return state


def node_reject(state: TrailerState) -> TrailerState:
    state["status"] = "rejected"
    state["decision_log"].append(log_event("unresolved_reject", {"failures": state["validation"]["failures"]}))
    return state


def route_after_validation(state: TrailerState) -> str:
    if state["validation"]["status"] in ("PASS", "PASS_WITH_WARNINGS"):
        return "finalize"
    if state["repair_attempts"] >= MAX_REPAIR_ATTEMPTS:
        return "reject"
    return "repair"


def build_trailer_graph():
    graph = StateGraph(TrailerState)

    graph.add_node("plan_audience_strategy", node_plan_audience_strategy)
    graph.add_node("generate_candidates", node_generate_candidates)
    graph.add_node("validate", node_validate)
    graph.add_node("repair", node_repair)
    graph.add_node("finalize", node_finalize)
    graph.add_node("reject", node_reject)

    graph.set_entry_point("plan_audience_strategy")
    graph.add_edge("plan_audience_strategy", "generate_candidates")
    graph.add_edge("generate_candidates", "validate")
    graph.add_conditional_edges("validate", route_after_validation,
        {"finalize": "finalize", "repair": "repair", "reject": "reject"})
    graph.add_edge("repair", "validate")   # loop back for re-validation
    graph.add_edge("finalize", END)
    graph.add_edge("reject", END)

    return graph.compile(checkpointer=MemorySaver())