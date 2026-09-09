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
