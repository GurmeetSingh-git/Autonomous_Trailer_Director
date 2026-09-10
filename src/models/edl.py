"""Edit decision list schemas and export helpers."""

from typing import Any

from pydantic import BaseModel, Field


class EDLClip(BaseModel):
    """One clip in an edit decision list."""

    scene_id: str
    start: float = 0.0
    end: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EDLSegment(BaseModel):
    """Assignment-facing segment with auditable editorial metadata."""

    id: str
    label: str
    scene_id: str
    source_in: str
    source_out: str
    tone: str
    audio: str
    subtitle: str
    reason: str
    evidence: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    is_included: bool = True


class EDL(BaseModel):
    """Ordered trailer edit decision list."""

    trailer_id: str = ""
    audience: str = ""
    duration_seconds: float = 0.0
    audience_promise: str = ""
    segments: list[EDLSegment] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    # Kept for callers that consume the original graph EDL shape.
    clips: list[EDLClip] = Field(default_factory=list)
    title: str = ""
    duration: float = 0.0


def _timecode(seconds: float) -> str:
    """Format seconds using the assignment's HH:MM:SS representation."""
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _segment_validation(segment: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    """Attach only checks and failures that identify this segment."""
    scene_id = segment.get("scene_id")
    failures = [failure for failure in validation.get("failures", []) if failure.get("scene_id") == scene_id]
    checks = [check for check in validation.get("checks", []) if check.get("status") in ("fail", "warning")]
    status = "FAIL" if failures else "PASS_WITH_WARNINGS" if checks else "PASS"
    return {"status": status, "failures": failures, "checks": checks}


def _evidence_with_contract(segment: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Preserve source evidence and make contract clearance auditable."""
    evidence = list(segment.get("evidence", []))
    cleared = set(state.get("constraint_map", {}).get("metadata", {}).get("cleared_scene_ids", []))
    scene_id = segment.get("scene_id", "unknown")
    contract_link = f"contract:scene-clearance:{scene_id}" if scene_id in cleared else "contract:pending-human-clearance"
    if contract_link not in evidence:
        evidence.append(contract_link)
    return evidence


def build_edl(state: dict[str, Any]) -> dict[str, Any]:
    """Convert validated graph segments into the assignment-facing EDL."""
    validation = state.get("validation", {})
    raw_segments = state.get("segments", [])
    clips = [EDLClip(scene_id=clip["scene_id"], start=clip["start"], end=clip["end"], metadata=clip) for clip in raw_segments]
    segments = [
        EDLSegment(
            id=segment.get("id", chr(ord("a") + index)),
            label=segment.get("label", f"Scene {segment['scene_id']}"),
            scene_id=segment["scene_id"],
            source_in=_timecode(float(segment.get("source_in", segment.get("start", 0)))),
            source_out=_timecode(float(segment.get("source_out", segment.get("end", 0)))),
            tone=segment.get("tone", ""),
            audio=segment.get("audio", "original_dialogue"),
            subtitle=segment.get("subtitle", "source_subtitles"),
            reason=segment.get("reason", ""),
            evidence=_evidence_with_contract(segment, state),
            risk_flags=segment.get("risk_flags", []),
            validation=_segment_validation(segment, validation),
            is_included=segment.get("is_included", True),
        )
        for index, segment in enumerate(raw_segments)
    ]
    duration = sum(clip.end - clip.start for clip in clips)
    edl = EDL(
        trailer_id=state.get("trailer_id", f"{state.get('audience', 'trailer')}_v1"),
        audience=state.get("audience", ""),
        duration_seconds=duration,
        audience_promise=state.get("audience_promise", ""),
        segments=segments,
        validation=validation,
        clips=clips,
        title=state.get("audience", "trailer"),
        duration=duration,
    )
    return edl.model_dump()
