"""Selective vision analysis: only for shots build_shot_records() flagged.

Extracts a few representative frames per flagged shot with ffmpeg, sends
them (not the whole clip) to the vision-capable LLM alongside the audio
context already known for that shot, and patches the ShotRecord in place.
Rechecking a shot means calling analyze_shot_visual() again with different
frame timestamps — never reprocessing the episode.
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from src.llm.client import LLMClient
from src.models.shot import ShotRecord, ShotVisual, ShotVisualBatch

logger = logging.getLogger(__name__)

VISION_PROMPT = """
You are looking at {n} frames sampled from a single shot of a TV episode,
covering roughly {start:.1f}s to {end:.1f}s. The known audio for this shot
is provided as context. Fill in only what is visually confirmable from
these frames: who appears, notable appearance details, actions taking
place, the location, and visible objects. Do not repeat information that
is already fully covered by the audio context. Do not guess at anything
outside these frames. Also set is_credit_or_title to true when this is an
opening/closing credit, cast/crew/producer name overlay, production logo,
rating certificate, opening title, or title card that replaces story footage.
Do not flag incidental text that is part of the story, such as posters,
election materials, banners, signs, or writing on props. If people are
performing a story action in a real location, treat it as story footage even
when text is visible in the frame.
"""


def _probe_media_duration(video_path: str) -> float | None:
    """Return the encoded duration when ffprobe is available."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            check=True,
            capture_output=True,
            text=True,
        )
        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except (OSError, ValueError, subprocess.CalledProcessError):
        logger.debug("Could not probe media duration for %s", video_path, exc_info=True)
        return None


def extract_frames(
    video_path: str,
    start: float,
    end: float,
    output_dir: Path,
    count: int = 3,
    timestamps: list[float] | None = None,
) -> list[Path]:
    """Pull `count` evenly spaced frames from [start, end] with ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)
    media_duration = _probe_media_duration(video_path)
    if media_duration is not None:
        last_seek = max(0.0, media_duration - 0.05)
        start = min(max(start, 0.0), last_seek)
        end = min(max(end, start), last_seek)
    else:
        start = max(start, 0.0)
        end = max(end, start)
    duration = max(end - start, 0.01)
    sample_times = timestamps or (
        [start]
        if count == 1
        else [start + duration * (i / (count - 1)) for i in range(count)]
    )
    sample_times = [
        min(max(timestamp, 0.0), last_seek) if media_duration is not None
        else max(timestamp, 0.0)
        for timestamp in sample_times
    ]
    frame_paths: list[Path] = []
    for index, timestamp in enumerate(sample_times):
        frame_path = output_dir / f"frame_{index}.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path,
            "-frames:v", "1", "-q:v", "2", str(frame_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as first_error:
            retry_timestamp = max(0.0, timestamp - 0.5)
            if retry_timestamp >= timestamp:
                raise
            logger.warning(
                "FFmpeg could not seek to %.3fs in %s; retrying at %.3fs",
                timestamp,
                video_path,
                retry_timestamp,
            )
            retry_cmd = [
                "ffmpeg", "-y", "-ss", str(retry_timestamp), "-i", video_path,
                "-frames:v", "1", "-q:v", "2", str(frame_path),
            ]
            try:
                subprocess.run(retry_cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError:
                raise first_error
        frame_paths.append(frame_path)
    return frame_paths


def analyze_shot_visual(
    shot: ShotRecord,
    video_path: str,
    llm: LLMClient,
    frame_count: int = 3,
    model: str | None = None,
) -> ShotRecord:
    """Extract frames for one flagged shot and patch in its visual fields.

    Call this again with a higher frame_count (or after nudging start/end
    slightly) to implement the recheck loop from a caller that decides a
    shot's first pass was still ambiguous — this function itself is stateless.
    """
    with tempfile.TemporaryDirectory(prefix=f"shot-{shot.shot_id}-") as tmp:
        frame_paths = extract_frames(video_path, shot.start, shot.end, Path(tmp), frame_count)
        prompt = VISION_PROMPT.format(n=len(frame_paths), start=shot.start, end=shot.end)
        try:
            visual = llm.generate_structured(
                system_prompt=prompt,
                media=[str(path) for path in frame_paths],
                context={"audio": shot.audio.model_dump(), "shot_id": shot.shot_id},
                response_schema=ShotVisual,
                cache_key=f"{shot.shot_id}-visual-{frame_count}f",
                model=model,
            )
        except Exception:
            logger.exception("Vision pass failed for shot %s; leaving audio_only", shot.shot_id)
            return shot

    updated = shot.model_copy()
    updated.visual = visual
    updated.coverage = "frame_confirmed"
    return updated


def group_shots_for_vision(
    shots: list[ShotRecord],
    max_group_shots: int = 12,
    max_group_duration: float = 45.0,
) -> list[list[ShotRecord]]:
    """Batch nearby shots needing visual evidence into bounded model calls."""
    groups: list[list[ShotRecord]] = []
    current_run: list[ShotRecord] = []

    for shot in shots:
        if not shot.visual_needed:
            continue
        if current_run and (
            len(current_run) >= max_group_shots
            or shot.end - current_run[0].start > max_group_duration
        ):
            groups.append(current_run)
            current_run = []
        current_run.append(shot)

    if current_run:
        groups.append(current_run)

    return groups


def _build_contact_sheet(
    frame_paths: list[Path], shots: list[ShotRecord], output_path: Path
) -> Path:
    if len(frame_paths) != len(shots):
        raise ValueError("Visual contact sheet requires exactly one frame per shot.")
    columns = 3
    tile_width, tile_height = 640, 360
    rows = math.ceil(len(frame_paths) / columns)
    sheet = np.zeros((rows * tile_height, columns * tile_width, 3), dtype=np.uint8)

    for index, (frame_path, shot) in enumerate(zip(frame_paths, shots)):
        frame = cv2.imread(str(frame_path))
        if frame is None:
            raise RuntimeError(f"Could not read extracted frame for {shot.shot_id}.")
        frame = cv2.resize(frame, (tile_width, tile_height), interpolation=cv2.INTER_AREA)
        label = f"{shot.shot_id}  {shot.start:.1f}-{shot.end:.1f}s"
        cv2.rectangle(frame, (0, 0), (tile_width, 34), (0, 0, 0), thickness=-1)
        cv2.putText(frame, label, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        row, column = divmod(index, columns)
        y, x = row * tile_height, column * tile_width
        sheet[y:y + tile_height, x:x + tile_width] = frame

    if not cv2.imwrite(str(output_path), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88]):
        raise RuntimeError("Could not write the visual-analysis contact sheet.")
    return output_path


def analyze_shot_group_visual(
    group: list[ShotRecord],
    video_path: str,
    llm: LLMClient,
    model: str | None = None,
) -> list[ShotRecord]:
    """Analyze one labeled frame per shot in one request with shot-specific results."""
    if len(group) == 1:
        return [analyze_shot_visual(group[0], video_path, llm, model=model)]

    start = group[0].start
    end = group[-1].end
    with tempfile.TemporaryDirectory(
        prefix=f"shots-{group[0].shot_id}-{group[-1].shot_id}-"
    ) as temp_dir:
        temp_path = Path(temp_dir)
        frame_paths = extract_frames(
            video_path,
            start,
            end,
            temp_path,
            timestamps=[(shot.start + shot.end) / 2 for shot in group],
        )
        contact_sheet = _build_contact_sheet(
            frame_paths, group, temp_path / "contact-sheet.jpg"
        )
        try:
            batch = llm.generate_structured(
                system_prompt=(
                    "The attached contact sheet contains one frame per shot, ordered "
                    "left-to-right and top-to-bottom. Each frame is labeled with its "
                    "shot ID and source time. Return one visual description for every "
                    "listed shot, using only what is visible in that shot's frame. Do "
                    "not copy actions, locations, people, or objects from one shot to "
                    "another. Classify opening/closing credits, cast/crew overlays, "
                    "production logos, rating certificates, opening titles, and title "
                    "cards. Each result must use the exact corresponding shot_id from "
                    "the audio context."
                ),
                media=str(contact_sheet),
                context={
                    "shots": [
                        {
                            "shot_id": shot.shot_id,
                            "start": shot.start,
                            "end": shot.end,
                            "audio": shot.audio.model_dump(),
                        }
                        for shot in group
                    ]
                },
                response_schema=ShotVisualBatch,
                cache_key=f"{group[0].shot_id}-{group[-1].shot_id}-visual-batch",
                model=model,
            )
        except Exception:
            logger.exception(
                "Batched vision pass failed for shots %s-%s; leaving audio_only",
                group[0].shot_id, group[-1].shot_id,
            )
            return group

    visual_by_id = {result.shot_id: result.visual for result in batch.shots}
    updated_group: list[ShotRecord] = []
    for shot in group:
        visual = visual_by_id.get(shot.shot_id)
        if visual is None:
            logger.warning("Batched vision response omitted shot %s", shot.shot_id)
            updated_group.append(shot)
            continue
        updated = shot.model_copy()
        updated.visual = visual
        updated.coverage = "frame_confirmed"
        updated_group.append(updated)
    return updated_group


def run_vision_pass(
    shots: list[ShotRecord],
    video_path: str,
    llm: LLMClient,
    model: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[ShotRecord]:
    """Run batched visual analysis, reporting completed and total visual shots."""
    groups = group_shots_for_vision(shots)
    total_visual_shots = sum(shot.visual_needed for shot in shots)
    visual_results: dict[str, ShotRecord] = {}
    completed_visual_shots = 0
    logger.info(
        "Starting visual analysis for %d shots in %d model calls.",
        total_visual_shots, len(groups),
    )
    if progress_callback:
        progress_callback(completed_visual_shots, total_visual_shots)

    for group in groups:
        if len(group) == 1:
            analyzed_group = [analyze_shot_visual(group[0], video_path, llm, model=model)]
        else:
            analyzed_group = analyze_shot_group_visual(group, video_path, llm, model=model)
        visual_results.update({shot.shot_id: shot for shot in analyzed_group})
        completed_visual_shots += len(group)
        if progress_callback:
            progress_callback(completed_visual_shots, total_visual_shots)
    return [visual_results.get(shot.shot_id, shot) for shot in shots]


def recheck_shot(
    shot: ShotRecord, video_path: str, llm: LLMClient, frame_count: int = 5, model: str | None = None
) -> ShotRecord:
    """Targeted re-extraction for one shot a downstream consumer flagged as
    still ambiguous after the first vision pass. Uses more frames by default."""
    return analyze_shot_visual(shot, video_path, llm, frame_count=frame_count, model=model)