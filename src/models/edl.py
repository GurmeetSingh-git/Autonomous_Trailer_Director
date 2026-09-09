"""Edit decision list schemas."""

from typing import Any

from pydantic import BaseModel, Field


class EDLClip(BaseModel):
    """One clip in an edit decision list."""

    scene_id: str
    start: float = 0.0
    end: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class EDL(BaseModel):
    """Ordered trailer edit decision list."""

    title: str = ""
    clips: list[EDLClip] = Field(default_factory=list)
    duration: float = 0.0


def build_edl(state: dict[str, Any]) -> dict[str, Any]:
    """Convert validated graph segments into the shared EDL contract."""
    clips = [EDLClip(scene_id=clip["scene_id"], start=clip["start"], end=clip["end"], metadata=clip) for clip in state.get("segments", [])]
    edl = EDL(title=state.get("audience", "trailer"), clips=clips, duration=sum(clip.end - clip.start for clip in clips))
    return edl.model_dump()
