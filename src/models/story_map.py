"""Story map schema."""

from typing import Any

from pydantic import BaseModel, Field


class StoryMap(BaseModel):
    """Structured understanding of an episode's story."""

    title: str = ""
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    dialogue: str = ""
