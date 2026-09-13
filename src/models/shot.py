"""Shot-level schema: the ground-truth unit beneath narrative scenes.

A ShotRecord is never fully authored by an LLM. PySceneDetect supplies
start/end; audio events are attached by code via timestamp overlap; visual
fields start empty and are only filled in by a targeted vision-LLM call
when `visual_needed` says so.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Coverage = Literal["audio_only", "frame_confirmed", "needs_recheck"]


class ShotAudio(BaseModel):
    dialogue: str = ""
    events: list[str] = Field(default_factory=list)


class ShotVisual(BaseModel):
    """Fields a vision LLM call is allowed to fill in for one shot."""

    characters: list[str] = Field(default_factory=list)
    appearance: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    location: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)


class ShotRecord(BaseModel):
    shot_id: str
    start: float
    end: float
    audio: ShotAudio = Field(default_factory=ShotAudio)
    visual: ShotVisual = Field(default_factory=ShotVisual)
    coverage: Coverage = "audio_only"
    visual_needed: bool = False
    scene_id: str | None = None  # filled in once shots are grouped into scenes