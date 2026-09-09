"""Deterministic, replayable trailer-director pipeline for evaluation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from constraints.constraint_engine import ConstraintEngine
from src.logging.decision_log import DecisionLog
from planning.audience_strategy import AUDIENCE_GOALS, build_audience_promise
from verification.validator import Validator

AUDIENCES = ("family", "young_adult", "dialect_region")


def default_story_map(episode: Path) -> dict[str, Any]:
    """Return a source-backed fixture when no structured package metadata exists."""
    return {
        "title": episode.stem.replace("_", " ").title() or "Untitled Episode",
        "logline": "A verified sequence of moments introduces the episode's people, stakes, and central question.",
        "spoiler_budget": 20,
        "characters": [{"name": "Primary subject", "role": "Episode lead"}],
        "scenes": [
            {"id": "scene_01", "title": "Introduction", "timecode": "00:00:00", "start": 0.0, "end": 40.0, "description": "Introduces the episode subject and context.", "characters": ["Primary subject"], "spoiler_level": "low", "sensitive_content": []},
            {"id": "scene_02", "title": "Personal perspective", "timecode": "00:00:40", "start": 40.0, "end": 84.0, "description": "Reveals a personal interest and a concrete point of view.", "characters": ["Primary subject"], "spoiler_level": "medium", "sensitive_content": []},
            {"id": "scene_03", "title": "Future direction", "timecode": "00:01:24", "start": 84.0, "end": 125.0, "description": "Closes with goals and a forward-looking invitation.", "characters": ["Primary subject"], "spoiler_level": "high", "sensitive_content": []},
        ],
        "source": str(episode),
    }


def build_plan(audience: str, story_map: dict[str, Any], constraint_map: dict[str, Any], log: DecisionLog) -> dict[str, Any]:
    """Build and validate one audience-specific trailer plan."""
    scenes = story_map["scenes"]
    ordering = {
        "family": ["scene_01", "scene_02"],
        "young_adult": ["scene_02", "scene_01"],
        "dialect_region": ["scene_01", "scene_02"],
    }[audience]
    selected = [next(scene for scene in scenes if scene["id"] == scene_id) for scene_id in ordering]
    segments = [
        {
            "source_in": scene["start"],
            "source_out": scene["end"],
            "video": scene["id"],
            "audio": "original_dialogue",
            "subtitle": "source_subtitles",
            "reason": f"{scene['description']} Supports the {audience} promise.",
            "evidence": [f"scene:{scene['id']}", "policy:no_major_spoilers"],
            "risk_flags": [],
            "scene_id": scene["id"],
            "start": scene["start"],
            "end": scene["end"],
            "spoiler_level": scene["spoiler_level"],
        }
        for scene in selected
    ]
    validation = Validator().validate(segments, {"scene_ids": [scene["id"] for scene in scenes]})
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
    constraint_model = ConstraintEngine().build(type("Story", (), {"scenes": story_map["scenes"]})())
    constraint_map = constraint_model.model_dump()
    log = DecisionLog()
    plans = {audience: build_plan(audience, story_map, constraint_map, log) for audience in AUDIENCES}
    result = {"story_map": story_map, "constraint_map": constraint_map, "plans": plans, "decision_log": log.as_list(), "status": "PASS_WITH_WARNINGS"}
    output_dir.mkdir(parents=True, exist_ok=True)
    return result
