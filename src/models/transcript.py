"""Transcript schema: the fine-grained, verbatim companion to GeneratedStoryMap.

GeneratedStoryMap answers "what's the narrative arc" (coarse, thematic).
AudioTranscript answers "who said what, when" (fine, verbatim). Keeping
them as separate LLM calls with separate prompts is what fixes the
5-scenes-for-158-seconds problem — a single prompt was being asked to do
both jobs and defaulted to the coarse one.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float
    end: float
    speaker: str = ""          # "" if speaker can't be distinguished
    dialogue: str = ""         # verbatim or as-close-as-audible; "" if non-verbal
    events: list[str] = Field(default_factory=list)  # e.g. "door slams", "music starts"


class AudioTranscript(BaseModel):
    segments: list[TranscriptSegment] = Field(default_factory=list)