from pathlib import Path

from api import StoryScene, normalize_scenes, trailer_from_plan
from orchestration.pipeline import AUDIENCES, run_director
from verification.validator import Validator
from models.edl import build_edl


def test_replay_generates_three_distinct_audience_plans(tmp_path: Path) -> None:
    result = run_director(tmp_path / "episode", tmp_path / "submission")
    assert set(result["plans"]) == set(AUDIENCES)
    assert result["plans"]["family"]["segments"] != result["plans"]["young_adult"]["segments"]
    assert all(plan["validation"]["status"] != "REJECT" for plan in result["plans"].values())


def test_replay_uses_content_aware_edit_ranges(tmp_path: Path) -> None:
    result = run_director(tmp_path / "episode", tmp_path / "submission")
    segments = result["plans"]["family"]["segments"]

    assert [(segment["source_in"], segment["source_out"]) for segment in segments] == [(0.0, 15.0), (40.0, 55.0)]


def test_uploaded_scene_ranges_are_content_aware_and_bounded(tmp_path: Path) -> None:
    scenes = [
        StoryScene(
            id="scene_01",
            title="Opening beat",
            timecode="00:00:00",
            end_timecode="00:00:40",
            content_start_timecode="00:00:04",
            content_end_timecode="00:00:19",
            description="The subject notices a clue.",
        ),
        StoryScene(
            id="scene_02",
            title="Fallback beat",
            timecode="00:00:40",
            end_timecode="00:01:10",
            description="The subject follows the clue.",
        ),
    ]

    normalized = normalize_scenes(scenes, tmp_path / "missing.mp4")

    assert (normalized[0]["trailerStart"], normalized[0]["trailerEnd"]) == (4.0, 19.0)
    assert (normalized[1]["trailerStart"], normalized[1]["trailerEnd"]) == (40.0, 55.0)


def test_validator_rejects_missing_scene() -> None:
    result = Validator().validate(
        [{"scene_id": "missing", "start": 0, "end": 4, "spoiler_level": "low"}],
        {"scene_ids": ["scene_01"]},
    )
    assert result["status"] == "REJECT"
    assert result["failures"][0]["check"] == "existence"


def test_validator_rejects_spoiler_and_invalid_timing() -> None:
    result = Validator().validate(
        [{"scene_id": "scene_01", "start": 4, "end": 4, "reason": "ending choice", "spoiler_level": "low"}],
        {"scene_ids": ["scene_01"], "protected_facts": [{"id": "ending_choice", "keywords": ["ending choice"], "first_revealed_in": "scene_01"}]},
    )
    assert result["status"] == "REJECT"
    failure_checks = {failure["check"] for failure in result["failures"]}
    assert {"spoiler", "timing"}.issubset(failure_checks)


def test_edl_exports_auditable_assignment_segments() -> None:
    edl = build_edl({
        "audience": "family",
        "audience_promise": "Warmth and broad entertainment value",
        "segments": [{
            "scene_id": "scene_01",
            "start": 13.0,
            "end": 27.0,
            "source_in": 13.0,
            "source_out": 27.0,
            "tone": "Calm",
            "audio": "dialogue_and_music",
            "subtitle": "standard_track",
            "reason": "Establishes the setup safely.",
            "evidence": ["scene:scene_01", "policy:no_major_spoilers"],
            "risk_flags": [],
        }],
        "validation": {"status": "PASS", "failures": [], "checks": []},
        "constraint_map": {"metadata": {"cleared_scene_ids": []}},
    })

    segment = edl["segments"][0]
    assert segment["source_in"] == "00:00:13"
    assert segment["audio"] == "dialogue_and_music"
    assert segment["evidence"][-1] == "contract:pending-human-clearance"
    assert segment["validation"]["status"] == "PASS"


def test_api_trailer_export_keeps_required_segment_metadata() -> None:
    trailer = trailer_from_plan(
        "run-1",
        {
            "trailer_id": "family_v1",
            "audience": "family",
            "duration_seconds": 14.0,
            "audience_promise": "Communicate warmth",
            "segments": [{
                "video": "scene_1",
                "scene_id": "scene_1",
                "source_in": 54.0,
                "source_out": 87.0,
                "start": 54.0,
                "end": 87.0,
                "tone": "affectionate",
                "audio": "dialogue_and_music",
                "subtitle": "standard_track",
                "reason": "Establishes the relationship safely.",
                "evidence": ["scene:scene_1"],
                "risk_flags": [],
            }],
            "validation": {"status": "PASS_WITH_WARNINGS", "checks": []},
        },
        "Episode",
    )

    segment = trailer["segments"][0]
    assert segment["source_in"] == "00:00:54"
    assert segment["source_out"] == "00:01:27"
    assert segment["evidence"][-1] == "contract:pending-human-clearance"
    assert segment["reason"]
    assert segment["is_included"] is True


def test_api_trailer_export_escalates_warning_status() -> None:
    trailer = trailer_from_plan(
        "run-1",
        {
            "audience": "family",
            "duration_seconds": 1.0,
            "segments": [],
            "validation": {
                "status": "PASS",
                "checks": [{"name": "Rights", "status": "warning", "detail": "Approval pending"}],
            },
        },
        "Episode",
    )

    assert trailer["validation"]["status"] == "PASS_WITH_WARNINGS"


def test_plot_reprocess_removes_requested_beat() -> None:
    from api import PlotReprocessRequest, reprocess_plot

    result = reprocess_plot(
        "8512d486-4a36-4005-a5a8-5d12e40baf55",
        PlotReprocessRequest(feedback="Remove third beat"),
        "family",
    )

    assert len(result["narrative_arc"]) == 2


def test_plot_reprocess_forwards_freeform_feedback_to_llm(monkeypatch) -> None:
    from types import SimpleNamespace

    import api
    from api import PlotReprocessRequest, reprocess_plot

    run = {
        "story_map": {
            "title": "Episode",
            "scenes": [{
                "id": "scene_01",
                "title": "Opening",
                "description": "Intro scene",
                "start": 0,
                "end": 30,
                "spoilerLevel": "low",
                "tone": "warm",
                "emotion": "wonder",
                "characters": ["Hero"],
                "trailerStart": 0,
                "trailerEnd": 15,
            }],
        },
        "trailer": {"audience": "family", "segments": []},
        "plans": {"family": {
            "audience": "family",
            "audience_promise": "Warm family story",
            "segments": [{
                "scene_id": "scene_01",
                "start": 0,
                "end": 15,
                "source_in": 0,
                "source_out": 15,
                "reason": "Establishes the scene",
                "evidence": ["scene:scene_01"],
                "spoiler_level": "low",
                "label": "Opening beat",
                "video": "scene_01",
            }],
            "duration_seconds": 15,
            "validation": {"status": "PASS", "checks": []},
        }},
        "constraint_map": {"metadata": {"scene_ids": ["scene_01"], "cleared_scene_ids": [], "expired_assets": [], "protected_facts": [], "max_cost_usd": 1.0}},
    }
    api.runs["llm-feedback-run"] = run

    captured = {}

    def fake_generate_structured(*args, **kwargs):
        captured["feedback"] = kwargs["context"]["director_feedback"]
        return SimpleNamespace(
            audience_promise="A warmer family promise",
            beats=[
                SimpleNamespace(
                    scene_id="scene_01",
                    beat_name="Opening with warmth",
                    emotional_goal="Establishes the family warmth.",
                    included=True,
                )
            ],
        )

    monkeypatch.setattr(api.os, "environ", {"GEMINI_API_KEY": "test-key"})
    monkeypatch.setattr(api.LLMClient, "generate_structured", fake_generate_structured)

    result = reprocess_plot(
        "llm-feedback-run",
        PlotReprocessRequest(feedback="Add one more beat and make the story more playful."),
        "family",
    )

    assert captured["feedback"] == "Add one more beat and make the story more playful."
    assert result["audience_promise"] == "A warmer family promise"
