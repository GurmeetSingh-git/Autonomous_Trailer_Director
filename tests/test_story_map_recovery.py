import json
from pathlib import Path
from types import SimpleNamespace

import api


def test_retry_story_map_uses_checkpoint_and_cleans_up(monkeypatch, tmp_path: Path) -> None:
    pending_dir = tmp_path / "pending"
    video_path = tmp_path / "episode.mp4"
    video_path.write_bytes(b"video")
    pending_dir.mkdir()
    checkpoint = {
        "audience": "family",
        "filename": "episode.mp4",
        "video_path": str(video_path),
        "selected_model": "gemini-3.5-flash-lite",
        "supporting_files": {},
        "detected_scenes": [],
        "shot_records": [{"shot_id": "shot-1"}],
    }
    pending_path = pending_dir / "run-1.json"
    pending_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    captured = {}

    class FakeLLM:
        def generate_structured(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(scenes=["scene"])

    def fake_finalize(*args):
        captured["finalize_args"] = args
        args[-1].unlink(missing_ok=True)

    monkeypatch.setattr(api, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(api, "LLMClient", lambda mode: FakeLLM())
    monkeypatch.setattr(api, "_complete_run_from_story_map", fake_finalize)

    result = api.retry_story_map("run-1", model="")

    assert result == {"runId": "run-1"}
    assert captured["media"] is None
    assert captured["context"]["shot_evidence"] == checkpoint["shot_records"]
    assert captured["finalize_args"][0] == "run-1"
    assert not pending_path.is_file()