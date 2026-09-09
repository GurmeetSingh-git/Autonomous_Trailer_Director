from pathlib import Path

from orchestration.pipeline import AUDIENCES, run_director
from verification.validator import Validator


def test_replay_generates_three_distinct_audience_plans(tmp_path: Path) -> None:
    result = run_director(tmp_path / "episode", tmp_path / "submission")
    assert set(result["plans"]) == set(AUDIENCES)
    assert result["plans"]["family"]["segments"] != result["plans"]["young_adult"]["segments"]
    assert all(plan["validation"]["status"] != "REJECT" for plan in result["plans"].values())


def test_validator_rejects_missing_scene() -> None:
    result = Validator().validate(
        [{"scene_id": "missing", "start": 0, "end": 4, "spoiler_level": "low"}],
        {"scene_ids": ["scene_01"]},
    )
    assert result["status"] == "REJECT"
    assert result["failures"][0]["check"] == "existence"


def test_validator_rejects_spoiler_and_invalid_timing() -> None:
    result = Validator().validate(
        [{"scene_id": "scene_01", "start": 4, "end": 4, "spoiler_level": "high"}],
        {"scene_ids": ["scene_01"]},
    )
    assert result["status"] == "REJECT"
    failure_checks = {failure["check"] for failure in result["failures"]}
    assert {"spoiler", "timing"}.issubset(failure_checks)
