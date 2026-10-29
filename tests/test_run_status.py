import asyncio
from io import BytesIO
from pathlib import Path
import subprocess

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile

import api


def test_create_run_schedules_analysis_and_returns_run_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(api, "RUNS_FILE", tmp_path / "runs.json")
    monkeypatch.setattr(api, "runs", {})
    background_tasks = BackgroundTasks()
    episode = UploadFile(filename="episode.mp4", file=BytesIO(b"video"))

    result = asyncio.run(api.create_run(
        background_tasks,
        episode,
        audience="family",
        model="gemini-test",
        scene_descriptions=None,
        dialogue_subtitles=None,
        policies_metadata=None,
    ))

    assert result["runId"] in api.runs
    assert api.runs[result["runId"]]["status"] == "processing"
    assert api.runs[result["runId"]]["stage"] == "queued"
    assert background_tasks.tasks[0].func is api.process_episode


def test_run_status_reports_processing_and_recovery(monkeypatch, tmp_path: Path) -> None:
    run_id = "run-1"
    monkeypatch.setattr(api, "runs", {
        run_id: {
            "status": "processing",
            "stage": "analyzing_visuals",
            "progress": {"processed": 12, "total": 60},
        },
    })
    monkeypatch.setattr(api, "PENDING_DIR", tmp_path)

    status = api.get_run_status(run_id)

    assert status == {
        "runId": run_id,
        "status": "processing",
        "stage": "analyzing_visuals",
        "error": None,
        "canRecover": False,
        "progress": {"processed": 12, "total": 60},
    }

    (tmp_path / f"{run_id}.json").write_text("{}", encoding="utf-8")
    assert api.get_run_status(run_id)["canRecover"] is True


def test_story_map_reports_processing_instead_of_missing_key(monkeypatch) -> None:
    monkeypatch.setattr(api, "runs", {
        "run-1": {"status": "processing", "stage": "detecting_scenes"},
    })

    with pytest.raises(HTTPException) as error:
        api.get_story_map("run-1")

    assert error.value.status_code == 409
    assert "still in progress (detecting_scenes)" in error.value.detail


def test_retry_rejects_processing_run_without_checkpoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "runs", {
        "run-1": {"status": "processing", "stage": "detecting_scenes"},
    })
    monkeypatch.setattr(api, "PENDING_DIR", tmp_path)

    with pytest.raises(HTTPException) as error:
        api.retry_story_map("run-1", model="")

    assert error.value.status_code == 409
    assert "still in progress (detecting_scenes)" in error.value.detail


def test_failed_story_map_exposes_failure_detail(monkeypatch) -> None:
    monkeypatch.setattr(api, "runs", {
        "run-1": {"status": "failed", "error": "FFmpeg missing"},
    })

    with pytest.raises(HTTPException) as error:
        api.get_story_map("run-1")

    assert error.value.status_code == 409
    assert error.value.detail == "FFmpeg missing"


def test_background_failure_is_persisted(monkeypatch, tmp_path: Path) -> None:
    run_id = "run-1"
    monkeypatch.setattr(api, "runs", {run_id: {"status": "processing", "stage": "queued"}})
    monkeypatch.setattr(api, "RUNS_FILE", tmp_path / "runs.json")
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path)

    def missing_ffmpeg() -> str:
        raise FileNotFoundError("FFmpeg missing")

    monkeypatch.setattr(api, "resolve_ffmpeg_path", missing_ffmpeg)

    api.process_episode(
        run_id,
        "family",
        "episode.mp4",
        tmp_path / "episode.mp4",
        {},
        "gemini-test",
    )

    assert api.runs[run_id]["status"] == "failed"
    assert api.runs[run_id]["stage"] == "failed"
    assert api.runs[run_id]["error"] == "FFmpeg missing"


def test_ffmpeg_failure_keeps_diagnostic_output(monkeypatch, tmp_path: Path) -> None:
    run_id = "run-ffmpeg"
    monkeypatch.setattr(api, "runs", {run_id: {"status": "processing", "stage": "queued"}})
    monkeypatch.setattr(api, "RUNS_FILE", tmp_path / "runs.json")
    monkeypatch.setattr(api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(api, "resolve_ffmpeg_path", lambda: "ffmpeg")

    def failed_ffmpeg(*args, **kwargs):
        raise subprocess.CalledProcessError(
            255,
            args[0],
            stderr="Input file has no audio stream",
        )

    monkeypatch.setattr(api.subprocess, "run", failed_ffmpeg)

    api.process_episode(
        run_id,
        "family",
        "episode.mp4",
        tmp_path / "episode.mp4",
        {},
        "gemini-test",
    )

    assert api.runs[run_id]["status"] == "failed"
    assert "exit code 255" in api.runs[run_id]["error"]
    assert "Input file has no audio stream" in api.runs[run_id]["error"]
