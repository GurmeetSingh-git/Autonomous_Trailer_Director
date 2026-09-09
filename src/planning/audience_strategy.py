# src/planning/audience_strategy.py

AUDIENCE_GOALS = {
    "family": "Communicate warmth, stakes, and broad entertainment value.",
    "young_adult": "Highlight pace, humour, identity, and character conflict.",
    "dialect_region": "Show cultural and linguistic familiarity without stereotyping.",
}


def build_audience_promise(audience: str, story_map: dict) -> str:
    """
    Commit to the audience promise BEFORE any clip selection happens.
    Stub version: returns a templated promise. Replace with an LLM call
    grounded in story_map's characters/events once story_map is real.
    """
    goal = AUDIENCE_GOALS.get(audience, "Engage the target audience appropriately.")
    return f"[STUB] Promise for '{audience}': {goal}"