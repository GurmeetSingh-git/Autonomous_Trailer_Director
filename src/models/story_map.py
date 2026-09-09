"""Story map schema."""

from typing import Any

from pydantic import BaseModel, Field


class ProtectedFact(BaseModel):
    """A spoiler-critical fact, curated independently of clip selection."""

    id: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    # Scenes where this fact is first established/revealed in the source episode.
    first_revealed_in: str | None = None


class StoryMap(BaseModel):
    """Structured understanding of an episode's story."""

    title: str = ""
    scenes: list[dict[str, Any]] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    dialogue: str = ""
    protected_facts: list[ProtectedFact] = Field(default_factory=list)