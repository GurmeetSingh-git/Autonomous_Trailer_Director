from pathlib import Path
import subprocess
from types import SimpleNamespace

from src.ingestion import vision_pass
from src.models.shot import ShotRecord, ShotVisual, ShotVisualBatch, ShotVisualResult


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


def test_visual_groups_are_bounded_by_shot_count_and_duration() -> None:
    shots = [
        ShotRecord(
            shot_id=f"shot-{index}",
            start=float(index * 3),
            end=float((index + 1) * 3),
            audio={"dialogue": "A spoken line."},
            visual_needed=True,
        )
        for index in range(25)
    ]

    groups = vision_pass.group_shots_for_vision(shots)

    assert [shot.shot_id for group in groups for shot in group] == [
        shot.shot_id for shot in shots
    ]
    assert all(len(group) <= 12 for group in groups)
    assert all(group[-1].end - group[0].start <= 45 for group in groups)
    assert len(groups) > 1


def test_visual_groups_batch_nearby_flagged_shots_across_unflagged_shots() -> None:
    shots = [
        ShotRecord(shot_id="first", start=0, end=2, visual_needed=True),
        ShotRecord(shot_id="clear", start=2, end=4, visual_needed=False),
        ShotRecord(shot_id="second", start=4, end=6, visual_needed=True),
    ]

    groups = vision_pass.group_shots_for_vision(shots)

    assert [[shot.shot_id for shot in group] for group in groups] == [["first", "second"]]


def test_batched_vision_returns_individual_visuals_for_each_shot(monkeypatch) -> None:
    shots = [
        ShotRecord(
            shot_id=f"shot-{index}",
            start=float(index * 2),
            end=float((index + 1) * 2),
            audio={"dialogue": f"Dialogue {index}"},
            visual_needed=True,
        )
        for index in range(2)
    ]
    calls = []

    monkeypatch.setattr(vision_pass, "extract_frames", lambda *args, **kwargs: [Path("one.jpg"), Path("two.jpg")])
    monkeypatch.setattr(vision_pass, "_build_contact_sheet", lambda frames, group, output: output)

    class FakeLLM:
        def generate_structured(self, **kwargs):
            calls.append(kwargs)
            return ShotVisualBatch(shots=[
                ShotVisualResult(
                    shot_id="shot-0",
                    visual=ShotVisual(actions=["opens a door"]),
                ),
                ShotVisualResult(
                    shot_id="shot-1",
                    visual=ShotVisual(actions=["enters the room"]),
                ),
            ])

    result = vision_pass.analyze_shot_group_visual(shots, "episode.mp4", FakeLLM())

    assert len(calls) == 1
    assert len(calls[0]["media"]) > 0
    assert calls[0]["response_schema"] is ShotVisualBatch
    assert [shot.visual.actions for shot in result] == [["opens a door"], ["enters the room"]]
    assert all(shot.coverage == "frame_confirmed" for shot in result)


def test_vision_progress_reports_visual_shots_after_each_batch(monkeypatch) -> None:
    shots = [
        ShotRecord(shot_id=f"shot-{index}", start=index * 2, end=(index + 1) * 2, visual_needed=True)
        for index in range(3)
    ] + [ShotRecord(shot_id="clear", start=6, end=8, visual_needed=False)]
    monkeypatch.setattr(
        vision_pass,
        "analyze_shot_group_visual",
        lambda group, *args, **kwargs: group,
    )
    progress = []

    result = vision_pass.run_vision_pass(
        shots,
        "episode.mp4",
        SimpleNamespace(),
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert result == shots
    assert progress == [(0, 3), (3, 3)]