# src/planning/audience_strategy.py
from pydantic import BaseModel

class AudiencePromise(BaseModel):
    promise: str  # one punchy sentence, specific to this episode


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


EMOTION_TONE_AFFINITY = {
    "family": {"wonder", "joy", "humour", "discovery", "calm"},
    "young_adult": {"tension", "stakes"},
    "dialect_region": {"discovery", "calm", "humour"},
}

def audience_scene_score(audience: str, scene: dict) -> int:
    """Score verified scene context against the requested audience lens."""
    signals = AUDIENCE_SIGNALS.get(audience, set())
    searchable = " ".join(str(scene.get(field, "")) for field in (
        "title", "description", "emotion", "tone", "dialogue", "characters",
    )).lower()
    keyword_score = sum(1 for signal in signals if signal in searchable)
    tone_emotion_score = sum(
        2 for field in ("tone", "emotion")
        if str(scene.get(field, "")).lower() in EMOTION_TONE_AFFINITY.get(audience, set())
    )
    character_bonus = len(scene.get("characters", [])) if audience == "dialect_region" else 0
    return keyword_score + tone_emotion_score + character_bonus



def build_audience_promise(audience: str, story_map: dict, llm=None) -> str:
    """
    Generate an audience-specific hook grounded in the actual episode content.
    Falls back to the deterministic template if no LLM client is supplied
    (e.g. replay/offline test mode).
    """
    goal = AUDIENCE_GOALS.get(audience, "Engage the target audience appropriately.")

    if llm is None:
        # offline fallback — deterministic, used in replay/tests
        return f"{goal} Ground the promise in the episode's verified characters and events."

    scenes = story_map.get("scenes", [])
    characters = story_map.get("characters", [])
    context = {
        "title": story_map.get("title", ""),
        "logline": story_map.get("logline", ""),
        "characters": characters,
        "scene_summaries": [
            {"id": s["id"], "description": s.get("description", ""), "emotion": s.get("emotion", "")}
            for s in scenes if s.get("spoiler_level") != "high"
        ],
    }
    prompt = f"""
Write ONE specific, exciting trailer promise sentence for the {audience} audience.
Goal for this audience: {goal}
Use only characters, events, and emotional beats that actually appear in the
supplied scene summaries. Do not invent plot points. Make it sound like a
trailer tagline, not a policy description — concrete, vivid, and grounded in
this episode's real content (name characters, name the concrete situation).
"""
    result = llm.generate_structured(
        system_prompt=prompt,
        context=context,
        response_schema=AudiencePromise,
        cache_key=f"promise-{audience}-{story_map.get('title','')}",
        model="gemini-3.5-flash-lite",
    )
    return result.promise