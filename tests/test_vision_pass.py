from pathlib import Path
import subprocess

from ingestion import vision_pass


def test_extract_frames_retries_a_near_end_seek(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(vision_pass, "_probe_media_duration", lambda _: None)

    def fake_run(command: list[str], **_: object) -> None:
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(4294967274, command)

    monkeypatch.setattr(vision_pass.subprocess, "run", fake_run)

    frames = vision_pass.extract_frames("episode.mp4", 272.5, 272.5, tmp_path, count=1)

    assert frames == [tmp_path / "frame_0.jpg"]
    assert calls[0][calls[0].index("-ss") + 1] == "272.5"
    assert calls[1][calls[1].index("-ss") + 1] == "272.0"