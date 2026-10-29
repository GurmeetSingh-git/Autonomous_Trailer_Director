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


def test_plot_reprocess_removes_requested_beat(monkeypatch) -> None:
    from types import SimpleNamespace

    import api
    from api import PlotReprocessRequest, reprocess_plot

    run = {
        "story_map": {
            "title": "Episode",
            "scenes": [{
                "id": "scene_01",
                "title": "Story",
                "description": "A story with three distinct moments",
                "start": 0,
                "end": 120,
                "spoilerLevel": "low",
                "sourceShots": [],
            }],
        },
        "trailer": {"audience": "family", "segments": []},
        "plans": {"family": {
            "audience": "family",
            "audience_promise": "A story",
            "segments": [{
                "scene_id": "scene_01",
                "start": 0,
                "end": 10,
                "source_in": 0,
                "source_out": 10,
                "reason": "A story moment",
                "evidence": ["scene:scene_01"],
                "spoiler_level": "low",
                "label": "Opening",
                "video": "scene_01",
            }],
            "duration_seconds": 10,
            "validation": {"status": "PASS", "checks": []},
        }},
        "constraint_map": {"metadata": {}},
    }

    def fake_generate_structured(*args, **kwargs):
        return SimpleNamespace(
            audience_promise="A story",
            beats=[
                SimpleNamespace(
                    scene_id="scene_01",
                    beat_name=f"A character choice {index}",
                    emotional_goal="A grounded moment",
                    source_in=f"00:00:{start:02d}.00",
                    source_out=f"00:00:{end:02d}.00",
                    included=True,
                )
                for index, (start, end) in enumerate(((10, 20), (40, 50), (80, 90)), start=1)
            ],
        )

    monkeypatch.setattr(api, "runs", {"isolated-remove-beat-run": run})
    monkeypatch.setattr(api, "save_runs", lambda: None)
    monkeypatch.setattr(api.os, "environ", {"GEMINI_API_KEY": "test-key"})
    monkeypatch.setattr(api.LLMClient, "generate_structured", fake_generate_structured)

    result = reprocess_plot(
        "isolated-remove-beat-run",
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
                "end": 60,
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
    monkeypatch.setattr(api, "runs", {"llm-feedback-run": run})
    monkeypatch.setattr(api, "save_runs", lambda: None)

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
                    source_in="00:00:20.00",
                    source_out="00:00:32.00",
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
    assert result["narrative_arc"][0]["source_in"] == "00:00:20.00"
    assert result["narrative_arc"][0]["source_out"] == "00:00:32.00"


def test_credit_and_title_shots_are_excluded_from_plot_selection() -> None:
    from api import is_credit_or_title_shot, is_generic_beat_name

    assert is_credit_or_title_shot({
        "visual": {"is_credit_or_title": True},
        "audio": {"dialogue": "", "events": []},
    })
    assert is_credit_or_title_shot({
        "visual": {"objects": ["rating certificate"]},
        "audio": {"dialogue": "", "events": []},
    })
    assert not is_credit_or_title_shot({
        "visual": {
            "is_credit_or_title": True,
            "actions": ["officials process voters at a registration desk"],
            "location": ["indoors at a registration desk"],
            "objects": ["papers", "forms"],
        },
        "audio": {"dialogue": "", "events": []},
    })
    assert is_credit_or_title_shot({
        "visual": {
            "is_credit_or_title": True,
            "actions": ["A scene plays behind opening credits."],
            "location": ["indoors"],
        },
        "audio": {"dialogue": "", "events": []},
    })
    assert not is_credit_or_title_shot({
        "visual": {"actions": ["two people meet"]},
        "audio": {"dialogue": "We should leave now.", "events": []},
    })
    assert is_generic_beat_name("The Initial Gathering Part One", "The Initial Gathering")
    assert not is_generic_beat_name("A necklace changes everything", "The Initial Gathering")


def test_accept_promise_arc_allows_specific_scene_title_but_rejects_episode_title(monkeypatch) -> None:
    import pytest

    import api
    from fastapi import HTTPException
    from api import PromiseArcUpdate, update_promise_arc

    scene = {
        "id": "scene_01",
        "title": "College Elections and Chaos",
        "start": 0,
        "end": 60,
        "spoilerLevel": "low",
        "sourceShots": ["story-shot"],
    }
    plan = {
        "audience": "family",
        "audience_promise": "A story of courage.",
        "segments": [],
        "duration_seconds": 0,
        "validation": {"status": "PASS", "checks": []},
    }
    run = {
        "story_map": {"title": "Tere Naam", "scenes": [scene]},
        "plans": {"family": plan},
        "constraint_map": {"metadata": {}},
        "shot_records": [{
            "shot_id": "story-shot",
            "start": 10,
            "end": 20,
            "audio": {"dialogue": "", "events": []},
            "visual": {
                "is_credit_or_title": True,
                "actions": ["officials process voters at a registration desk"],
                "location": ["indoors at a registration desk"],
                "objects": ["papers", "forms"],
            },
        }],
    }
    monkeypatch.setattr(api, "runs", {"promise-arc-run": run})
    monkeypatch.setattr(api, "save_runs", lambda: None)

    update = PromiseArcUpdate(
        audience_promise="A story of courage.",
        narrative_arc=[{
            "scene_id": "scene_01",
            "beat_name": scene["title"],
            "source_in": "00:00:10.00",
            "source_out": "00:00:20.00",
            "emotional_goal": "Rival factions clash over the election.",
        }],
    )
    result = update_promise_arc("promise-arc-run", update)

    assert result["promise_arc"]["narrative_arc"][0]["beat_name"] == scene["title"]
    update.narrative_arc[0].beat_name = "Tere Naam"
    with pytest.raises(HTTPException) as error:
        update_promise_arc("promise-arc-run", update)
    assert error.value.status_code == 422


def test_plot_reprocess_rejects_reused_beat_ranges(monkeypatch) -> None:
    from types import SimpleNamespace

    import pytest
    import api
    from fastapi import HTTPException
    from api import PlotReprocessRequest, reprocess_plot

    run = {
        "story_map": {
            "title": "Episode",
            "scenes": [{
                "id": "scene_01",
                "title": "Story",
                "description": "Two distinct story moments",
                "start": 0,
                "end": 60,
                "spoilerLevel": "low",
                "sourceShots": [],
            }],
        },
        "trailer": {"audience": "family", "segments": []},
        "plans": {
            "family": {
                "audience": "family",
                "segments": [],
                "audience_promise": "A story",
                "validation": {"status": "PASS", "checks": []},
            },
        },
        "constraint_map": {"metadata": {}},
    }

    def fake_generate_structured(*args, **kwargs):
        return SimpleNamespace(
            audience_promise="A story",
            beats=[
                SimpleNamespace(
                    scene_id="scene_01",
                    beat_name=name,
                    emotional_goal="A grounded moment",
                    source_in="00:00:10.00",
                    source_out="00:00:20.00",
                    included=True,
                )
                for name in ("First beat", "Second beat")
            ],
        )

    monkeypatch.setattr(api, "runs", {"duplicate-range-run": run})
    monkeypatch.setattr(api.os, "environ", {"GEMINI_API_KEY": "test-key"})
    monkeypatch.setattr(api.LLMClient, "generate_structured", fake_generate_structured)

    with pytest.raises(HTTPException) as error:
        reprocess_plot(
            "duplicate-range-run",
            PlotReprocessRequest(feedback="Create two beats"),
            "family",
        )

    assert error.value.status_code == 502


def test_requested_trailer_runtime_creates_discrete_clips(monkeypatch) -> None:
    from types import SimpleNamespace

    import api
    from api import PlotReprocessRequest, reprocess_plot

    run = {
        "story_map": {
            "title": "Episode",
            "scenes": [{
                "id": "scene_01",
                "title": "Story",
                "description": "Distinct story moments across the episode",
                "start": 0,
                "end": 600,
                "spoilerLevel": "low",
                "sourceShots": [],
            }],
        },
        "trailer": {"audience": "family", "segments": []},
        "plans": {
            "family": {
                "audience": "family",
                "segments": [],
                "audience_promise": "A story",
                "validation": {"status": "PASS", "checks": []},
            },
        },
        "constraint_map": {"metadata": {}},
    }
    captured = {}

    def fake_generate_structured(*args, **kwargs):
        captured.update(kwargs["context"])
        return SimpleNamespace(
            audience_promise="A trailer story",
            beats=[
                SimpleNamespace(
                    scene_id="scene_01",
                    beat_name=f"A rising story moment {index + 1}",
                    emotional_goal="Escalates the story.",
                    source_in=f"00:{start // 60:02d}:{start % 60:02d}.00",
                    source_out=f"00:{(start + 15) // 60:02d}:{(start + 15) % 60:02d}.00",
                    included=True,
                )
                for index, start in enumerate(range(0, 500, 25))
            ],
        )

    monkeypatch.setattr(api, "runs", {"five-minute-run": run})
    monkeypatch.setattr(api, "save_runs", lambda: None)
    monkeypatch.setattr(api.os, "environ", {"GEMINI_API_KEY": "test-key"})
    monkeypatch.setattr(api.LLMClient, "generate_structured", fake_generate_structured)

    result = reprocess_plot(
        "five-minute-run",
        PlotReprocessRequest(feedback="I need a 5 mins long trailer with 5-6 cuts"),
        "family",
    )

    assert captured["target_duration_seconds"] == 300
    assert captured["target_clip_count"] == 20
    assert result["target_duration_seconds"] == 300
    assert len(result["narrative_arc"]) == 20
    assert all(beat["text_card"] is None for beat in result["narrative_arc"])
    assert api.requested_duration_seconds("5 min trailer") == 300
    assert api.requested_cut_count("at least 5-6 cuts") == 6


def test_audience_reanalysis_returns_six_distinct_story_moments(monkeypatch) -> None:
    from types import SimpleNamespace

    import api

    scene = {
        "id": "scene_01",
        "title": "Episode title",
        "description": "A story changes over time",
        "start": 0,
        "end": 180,
        "trailer_start": 0,
        "trailer_end": 15,
        "spoiler_level": "low",
        "source_shots": [f"shot-{index}" for index in range(36)],
        "tone": "tension",
        "emotion": "stakes",
    }
    shots = [
        {
            "shot_id": f"shot-{index}",
            "start": index * 5,
            "end": (index + 1) * 5,
            "audio": {"dialogue": "", "events": []},
            "visual": {
                "actions": [f"story action {index}"],
                "is_credit_or_title": index == 0,
            },
        }
        for index in range(36)
    ]
    run = {
        "planning_story_map": {"title": "Episode", "scenes": [scene]},
        "story_map": {"title": "Episode", "scenes": [scene]},
        "shot_records": shots,
        "constraint_map": {"metadata": {}},
        "plans": {},
    }
    captured = {}

    def fake_generate_structured(*args, **kwargs):
        captured.update(kwargs["context"])
        return SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    scene_id="scene_01",
                    beat_name=f"Trailer moment {index + 1}",
                    source_in=f"00:00:{10 + index * 25:02d}.00",
                    source_out=f"00:00:{20 + index * 25:02d}.00",
                    emotional_goal="The stakes increase.",
                    transition_after="hard_cut",
                    transition_reason="A sharp shift raises energy.",
                )
                for index in range(6)
            ],
        )

    monkeypatch.setattr(api.LLMClient, "generate_structured", fake_generate_structured)

    plan = api.reanalyze_audience_plan("six-beat-run", run, "family")

    assert len(plan["segments"]) == 6
    assert len({(segment["start"], segment["end"]) for segment in plan["segments"]}) == 6
    evidence = captured["scenes"][0]["shot_evidence"]
    assert all(not shot["visual"]["is_credit_or_title"] for shot in evidence)


def test_requested_runtime_is_not_silently_ignored_without_live_model(monkeypatch) -> None:
    import pytest

    import api
    from fastapi import HTTPException
    from api import PlotReprocessRequest, reprocess_plot

    monkeypatch.setattr(api, "runs", {
        "no-model-run": {
            "story_map": {"title": "Episode", "scenes": []},
            "trailer": {"audience": "family", "segments": []},
            "plans": {},
            "constraint_map": {"metadata": {}},
        },
    })
    monkeypatch.setattr(api.os, "environ", {})

    with pytest.raises(HTTPException) as error:
        reprocess_plot(
            "no-model-run",
            PlotReprocessRequest(feedback="Make a 5 minute trailer"),
            "family",
        )

    assert error.value.status_code == 503
