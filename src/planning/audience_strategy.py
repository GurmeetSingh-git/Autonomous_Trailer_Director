# src/planning/audience_strategy.py

AUDIENCE_GOALS = {
    "family": "Communicate warmth, stakes, and broad entertainment value.",
    "young_adult": "Highlight pace, humour, identity, and character conflict.",
    "dialect_region": "Show cultural and linguistic familiarity without stereotyping.",
}

AUDIENCE_SIGNALS = {
    "family": {"warmth", "wonder", "joy", "humour", "hope", "discovery", "together", "heart"},
    "young_adult": {"tension", "stakes", "identity", "conflict", "grit", "choice", "pace", "rebellion"},
    "dialect_region": {"dialogue", "voice", "community", "family", "culture", "home", "language", "together"},
}


def audience_scene_score(audience: str, scene: dict) -> int:
    """Score verified scene context against the requested audience lens."""
    signals = AUDIENCE_SIGNALS.get(audience, set())
    searchable = " ".join(str(scene.get(field, "")) for field in (
        "title", "description", "emotion", "tone", "dialogue", "characters",
    )).lower()
    return sum(1 for signal in signals if signal in searchable)


def build_audience_promise(audience: str, story_map: dict) -> str:
    """
    Commit to the audience promise BEFORE any clip selection happens.
    Stub version: returns a templated promise. Replace with an LLM call
    grounded in story_map's characters/events once story_map is real.
    """
    goal = AUDIENCE_GOALS.get(audience, "Engage the target audience appropriately.")
    return f"{goal} Ground the promise in the episode's verified characters and events."