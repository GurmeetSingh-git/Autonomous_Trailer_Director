"""Smoke tests for the project structure and shared contracts."""

from llm.llm_client import LLMClient
from models import ConstraintMap, EDL, EDLClip, StoryMap
from orchestration.run_state import RunState


def test_shared_contracts_are_importable() -> None:
    assert LLMClient("mock").mode == "mock"
    assert RunState("test-run").run_id == "test-run"
    assert StoryMap().scenes == []
    assert ConstraintMap().policies == []
    assert EDL(clips=[EDLClip(scene_id="scene-1")]).clips[0].scene_id == "scene-1"
