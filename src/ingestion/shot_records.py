"""Combine the PySceneDetect shot timeline with audio-derived events.

This module is deliberately LLM-free. It takes:
  - `shots`: the output of detect_scene_cuts() -> [{id, start, end, ...}, ...]
  - `audio_events`: timestamped dialogue/events already extracted by the
    audio-only LLM call (see AudioEvent below)

and produces one ShotRecord per shot, with audio attached by simple
interval overlap and every visual field left empty. Nothing here invents
content — it only organizes what's already known.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.models.shot import ShotAudio, ShotRecord, ShotVisual


class AudioEvent(TypedDict, total=False):
    start: float
    end: float
    dialogue: str
    events: list[str]


def _overlap_seconds(event: AudioEvent, shot_start: float, shot_end: float) -> float:
    event_start = event.get("start", shot_start)
    event_end = event.get("end", event_start)
    return max(0.0, min(event_end, shot_end) - max(event_start, shot_start))


def assign_audio_to_shots(
    shots: list[dict[str, Any]], audio_events: list[AudioEvent]
) -> dict[str, ShotAudio]:
    """Bucket audio events onto shots by timestamp overlap.

    Each event's dialogue is attributed to exactly ONE shot — whichever
    shot it overlaps the most — instead of being copy-pasted into every
    shot it happens to span. Without this, a single long utterance that
    crosses several quick cuts would show up duplicated verbatim in each
    of those shots. Non-verbal `events` (music, laughter, etc.) are still
    attached to every overlapping shot, since those are ambient and don't
    suffer from the same duplication problem.

    A shot with no primary dialogue and no events gets an empty ShotAudio
    (silent shot), which is itself a meaningful signal for gap-detection.
    """
    shot_ids = [shot["id"] for shot in shots]
    dialogue_by_shot: dict[str, list[str]] = {shot_id: [] for shot_id in shot_ids}
    events_by_shot: dict[str, list[str]] = {shot_id: [] for shot_id in shot_ids}

    for event in audio_events:
        best_shot_id: str | None = None
        best_overlap = 0.0
        for shot in shots:
            shot_start, shot_end = float(shot["start"]), float(shot["end"])
            overlap = _overlap_seconds(event, shot_start, shot_end)
            if overlap > best_overlap:
                best_overlap = overlap
                best_shot_id = shot["id"]

            if overlap > 0:
                events_by_shot[shot["id"]].extend(event.get("events", []))

        if event.get("dialogue") and best_shot_id is not None:
            dialogue_by_shot[best_shot_id].append(event["dialogue"])

    return {
        shot_id: ShotAudio(
            dialogue=" ".join(dialogue_by_shot[shot_id]).strip(),
            events=events_by_shot[shot_id],
        )
        for shot_id in shot_ids
    }


def decide_visual_needed(audio: ShotAudio, min_dialogue_chars: int = 25) -> bool:
    """Heuristic gap-detection: flag shots where audio alone under-describes
    what's happening. Cheap and deterministic; swap in a lightweight LLM
    classification later only if this proves too coarse.

    Rules, in order:
      - No dialogue and no events at all -> definitely needs a visual check
        (fully silent shot; audio told us nothing).
      - Has events but no dialogue -> maybe (action described, but no
        detail on who/what/where) -> flagged for now, conservative default.
      - Has dialogue but it's very short -> maybe (a one-word line rarely
        carries scene-setting information).
      - Substantial dialogue and no bare action-only events -> not needed.
    """
    has_dialogue = bool(audio.dialogue.strip())
    has_events = bool(audio.events)

    if not has_dialogue and not has_events:
        return True
    if has_events and not has_dialogue:
        return True
    if has_dialogue and len(audio.dialogue.strip()) < min_dialogue_chars:
        return True
    return False


def build_shot_records(
    shots: list[dict[str, Any]], audio_events: list[AudioEvent]
) -> list[ShotRecord]:
    """Build the Step-4 JSON structure entirely in code.

    Visual fields are always initialized empty here — they are only ever
    populated later by analyze_shot_visual() in vision_pass.py, and only
    for shots where visual_needed is True.
    """
    audio_by_shot = assign_audio_to_shots(shots, audio_events)
    records: list[ShotRecord] = []
    for shot in shots:
        shot_id = shot["id"]
        audio = audio_by_shot[shot_id]
        records.append(
            ShotRecord(
                shot_id=shot_id,
                start=float(shot["start"]),
                end=float(shot["end"]),
                audio=audio,
                visual=ShotVisual(),
                coverage="audio_only",
                visual_needed=decide_visual_needed(audio),
            )
        )
    return records