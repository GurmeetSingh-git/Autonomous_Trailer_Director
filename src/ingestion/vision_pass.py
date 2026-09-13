"""Selective vision analysis: only for shots build_shot_records() flagged.

Extracts a few representative frames per flagged shot with ffmpeg, sends
them (not the whole clip) to the vision-capable LLM alongside the audio
context already known for that shot, and patches the ShotRecord in place.
Rechecking a shot means calling analyze_shot_visual() again with different
frame timestamps — never reprocessing the episode.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.llm.client import LLMClient
from src.models.shot import ShotRecord, ShotVisual

logger = logging.getLogger(__name__)

VISION_PROMPT = """
You are looking at {n} frames sampled from a single shot of a TV episode,
covering roughly {start:.1f}s to {end:.1f}s. The known audio for this shot
is provided as context. Fill in only what is visually confirmable from
these frames: who appears, notable appearance details, actions taking
place, the location, and visible objects. Do not repeat information that
is already fully covered by the audio context. Do not guess at anything
outside these frames.
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
    video_path: str, start: float, end: float, output_dir: Path, count: int = 3
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
    timestamps = (
        [start]
        if count == 1
        else [start + duration * (i / (count - 1)) for i in range(count)]
    )
    frame_paths: list[Path] = []
    for index, timestamp in enumerate(timestamps):
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


def group_shots_for_vision(shots: list[ShotRecord]) -> list[list[ShotRecord]]:
    """Group consecutive SILENT flagged shots into one unit for a shared
    vision call, while keeping every other shot (including flagged shots
    that have their own dialogue) as its own singleton group.

    A shot only joins a group if visual_needed is True AND it has no
    dialogue of its own — a shot with dialogue has its own audio context
    and shouldn't be blended into a neighboring silent run, even if both
    happen to be flagged. Groups are always contiguous in the original
    shot order; nothing here reorders or drops a shot.
    """
    groups: list[list[ShotRecord]] = []
    current_run: list[ShotRecord] = []

    def _is_silent_and_needed(shot: ShotRecord) -> bool:
        return shot.visual_needed and not shot.audio.dialogue.strip()

    for shot in shots:
        if _is_silent_and_needed(shot):
            current_run.append(shot)
            continue
        if current_run:
            groups.append(current_run)
            current_run = []
        groups.append([shot])

    if current_run:
        groups.append(current_run)

    return groups


def analyze_shot_group_visual(
    group: list[ShotRecord],
    video_path: str,
    llm: LLMClient,
    frames_per_shot: int = 2,
    max_frames: int = 8,
    model: str | None = None,
) -> list[ShotRecord]:
    """Run ONE vision call spanning a run of consecutive silent shots, then
    apply the same result to every shot in the group.

    This trades per-shot precision for fewer, cheaper calls on stretches
    that are genuinely silent and contiguous — the model sees the whole
    span at once, which is often *more* informative for continuous action
    (e.g. someone walking down a corridor across several quick cuts) than
    isolating each cut individually.
    """
    if len(group) == 1:
        return [analyze_shot_visual(group[0], video_path, llm, model=model)]

    start = group[0].start
    end = group[-1].end
    frame_count = min(max_frames, max(3, frames_per_shot * len(group)))

    with tempfile.TemporaryDirectory(prefix=f"shots-{group[0].shot_id}-{group[-1].shot_id}-") as tmp:
        frame_paths = extract_frames(video_path, start, end, Path(tmp), frame_count)
        prompt = VISION_PROMPT.format(n=len(frame_paths), start=start, end=end) + (
            f"\n\nThese frames span {len(group)} consecutive silent shots "
            f"({group[0].shot_id} through {group[-1].shot_id}). Describe what "
            "is happening across this whole span, not just a single instant."
        )
        try:
            visual = llm.generate_structured(
                system_prompt=prompt,
                media=[str(path) for path in frame_paths],
                context={"shot_ids": [shot.shot_id for shot in group]},
                response_schema=ShotVisual,
                cache_key=f"{group[0].shot_id}-{group[-1].shot_id}-visual-group",
                model=model,
            )
        except Exception:
            logger.exception(
                "Grouped vision pass failed for shots %s-%s; leaving audio_only",
                group[0].shot_id, group[-1].shot_id,
            )
            return group

    updated_group = []
    for shot in group:
        updated = shot.model_copy()
        updated.visual = visual
        updated.coverage = "frame_confirmed"
        updated_group.append(updated)
    return updated_group


def run_vision_pass(
    shots: list[ShotRecord], video_path: str, llm: LLMClient, model: str | None = None
) -> list[ShotRecord]:
    """Run the vision pass on flagged shots, grouping consecutive silent
    runs into a single call each. Shots that aren't flagged pass through
    untouched; flagged shots with their own dialogue are still analyzed
    individually.
    """
    groups = group_shots_for_vision(shots)
    result: list[ShotRecord] = []
    for group in groups:
        if len(group) == 1:
            shot = group[0]
            result.append(
                analyze_shot_visual(shot, video_path, llm, model=model)
                if shot.visual_needed
                else shot
            )
        else:
            result.extend(analyze_shot_group_visual(group, video_path, llm, model=model))
    return result


def recheck_shot(
    shot: ShotRecord, video_path: str, llm: LLMClient, frame_count: int = 5, model: str | None = None
) -> ShotRecord:
    """Targeted re-extraction for one shot a downstream consumer flagged as
    still ambiguous after the first vision pass. Uses more frames by default."""
    return analyze_shot_visual(shot, video_path, llm, frame_count=frame_count, model=model)