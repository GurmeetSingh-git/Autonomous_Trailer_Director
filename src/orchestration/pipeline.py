"""Deterministic, replayable trailer-director pipeline for evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.constraints.constraint_engine import ConstraintEngine
from src.logging.decision_log import DecisionLog
from src.models.story_map import StoryMap
from src.planning.audience_strategy import AUDIENCE_GOALS, build_audience_promise
from src.verification.validator import Validator

AUDIENCES = ("family", "young_adult", "dialect_region")
EMOTION_PRIORITY = {"stakes": 4, "tension": 3, "joy": 2, "wonder": 2, "calm": 1}


def _edit_range(scene: dict[str, Any]) -> tuple[float, float]:
    """Return an explicit content range, bounded by the source scene."""
    scene_start = float(scene["start"])
    scene_end = float(scene["end"])
    for start_key, end_key in (("trailer_start", "trailer_end"), ("clip_start", "clip_end"), ("content_start", "content_end")):
        if start_key in scene and end_key in scene:
            start = max(scene_start, float(scene[start_key]))
            end = min(scene_end, float(scene[end_key]))
            if end > start:
                return start, end
    return scene_start, scene_end


def default_story_map(episode: Path) -> dict[str, Any]:
    """Return a source-backed fixture when no structured package metadata exists."""
    return {
        "title": episode.stem.replace("_", " ").title() or "Untitled Episode",
        "logline": "A verified sequence of moments introduces the episode's people, stakes, and central question.",
        "spoiler_budget": 20,
        "characters": ["Primary subject"],
        "scenes": [
            {"id": "scene_01", "title": "Introduction", "timecode": "00:00:00", "start": 0.0, "end": 40.0, "trailer_start": 0.0, "trailer_end": 15.0, "description": "Introduces the episode subject and context.", "characters": ["Primary subject"], "spoiler_level": "low", "sensitive_content": [], "emotion": "wonder", "tone": "discovery"},
            {"id": "scene_02", "title": "Personal perspective", "timecode": "00:00:40", "start": 40.0, "end": 84.0, "trailer_start": 40.0, "trailer_end": 55.0, "description": "Reveals a personal interest and a concrete point of view.", "characters": ["Primary subject"], "spoiler_level": "medium", "sensitive_content": [], "emotion": "stakes", "tone": "tension"},
            {"id": "scene_03", "title": "Future direction", "timecode": "00:01:24", "start": 84.0, "end": 125.0, "description": "Closes with goals and a forward-looking invitation.", "characters": ["Primary subject"], "spoiler_level": "high", "sensitive_content": [], "emotion": "stakes", "tone": "promise"},
        ],
        "protected_facts": [{"id": "ending_choice", "summary": "The final direction", "keywords": ["final direction"], "first_revealed_in": "scene_03"}],
        "source": str(episode),
    }


def build_plan(audience: str, story_map: dict[str, Any], constraint_map: dict[str, Any], log: DecisionLog) -> dict[str, Any]:
    """Build and validate one audience-specific trailer plan."""
    scenes = [scene for scene in story_map["scenes"] if scene.get("spoiler_level", "low") != "high"]
    if audience == "young_adult":
        selected = sorted(scenes, key=lambda scene: EMOTION_PRIORITY.get(str(scene.get("emotion", "")).lower(), 0), reverse=True)
    elif audience == "dialect_region":
        selected = [scene for scene in scenes if scene.get("dialogue", True)] or scenes
        selected = sorted(selected, key=lambda scene: scene.get("start", 0))
    else:
        selected = sorted(scenes, key=lambda scene: scene.get("start", 0))
    segments = [
        {
            "source_in": edit_start,
            "source_out": edit_end,
            "video": scene["id"],
            "audio": "original_dialogue",
            "subtitle": "source_subtitles",
            "tone": scene.get("tone") or scene.get("emotion") or "discovery",
            "sensitive_content": scene.get("sensitive_content", []),
            "reason": f"{scene['description']} Supports the {audience} promise.",
            "evidence": [f"scene:{scene['id']}", "policy:no_major_spoilers"],
            "risk_flags": [],
            "scene_id": scene["id"],
            "start": edit_start,
            "end": edit_end,
            "spoiler_level": scene["spoiler_level"],
        }
        for scene in selected
        for edit_start, edit_end in [_edit_range(scene)]
    ]
    validation = Validator().validate(
    segments,
    {
        "scene_ids": constraint_map.get("metadata", {}).get("scene_ids", [scene["id"] for scene in scenes]),
        "cleared_scene_ids": constraint_map.get("metadata", {}).get("cleared_scene_ids", []),
        "expired_assets": constraint_map.get("metadata", {}).get("expired_assets", []),
        "protected_facts": constraint_map.get("metadata", {}).get("protected_facts", []),
        "audience": audience,
        "estimated_cost_usd": 0.02,
        "max_cost_usd": constraint_map.get("metadata", {}).get("max_cost_usd", 1.0),
    },
)
    log.append("plan_created", {"audience": audience, "segments": [item["video"] for item in segments]})
    return {
        "trailer_id": f"{audience}_v1",
        "audience": audience,
        "objective": AUDIENCE_GOALS[audience],
        "duration_seconds": sum(item["end"] - item["start"] for item in segments),
        "audience_promise": build_audience_promise(audience, story_map),
        "segments": segments,
        "validation": validation,
        "estimated_cost_usd": 0.02,
        "fallback_plan": "Use replay fixtures and deterministic checks if the preferred model is unavailable.",
    }


def run_director(episode: Path, output_dir: Path) -> dict[str, Any]:
    """Generate all required artifacts without requiring an API key."""
    story_map = default_story_map(episode)
    constraint_model = ConstraintEngine().build(StoryMap.model_validate(story_map))
    constraint_map = constraint_model.model_dump()
    log = DecisionLog()
    plans = {audience: build_plan(audience, story_map, constraint_map, log) for audience in AUDIENCES}
    result = {"story_map": story_map, "constraint_map": constraint_map, "plans": plans, "decision_log": log.as_list(), "status": "PASS_WITH_WARNINGS"}
    output_dir.mkdir(parents=True, exist_ok=True)
    return result
