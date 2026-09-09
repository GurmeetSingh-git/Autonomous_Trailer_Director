from pathlib import Path

from api import StoryScene, normalize_scenes
from orchestration.pipeline import AUDIENCES, run_director
from verification.validator import Validator


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
