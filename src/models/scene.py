# src/models/scene.py
from enum import Enum
from pydantic import BaseModel, Field


class SpoilerRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class DialogueLine(BaseModel):
    speaker: str
    text: str
    start: str   # "HH:MM:SS.mmm"
    end: str


class Suitability(BaseModel):
    family: bool
    young_adult: bool
    dialect_region: bool


class SceneAnalysis(BaseModel):
    scene_id: str
    start: str
    end: str
    description: str
    visual_elements: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    location: str
    action: list[str] = Field(default_factory=list)
    emotion: str
    dialogue: list[DialogueLine] = Field(default_factory=list)
    spoiler_risk: SpoilerRisk
    spoiler_reason: str
    sensitive_content: list[str] = Field(default_factory=list)
    suitability: Suitability