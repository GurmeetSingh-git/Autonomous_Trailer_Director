"""Run this BEFORE the narrative STORY_MAP_PROMPT call, on the same
extracted audio file. It replaces "summarize the audio" with "transcribe
the audio" as a distinct job, which is what gives build_shot_records()
something fine-grained enough to actually attach to 32 shots instead of 5
broad scenes.
"""

from __future__ import annotations

from src.ingestion.shot_records import AudioEvent
from src.llm.client import LLMClient
from src.models.transcript import AudioTranscript

TRANSCRIPT_PROMPT = """
Transcribe this audio verbatim, segment by segment. Do not summarize, do
not paraphrase, and do not skip short or overlapping lines. Each segment
should be a single continuous utterance or a distinct non-verbal audio
event (e.g. music, a door closing, a long silence).

For each segment return:
- start and end time in seconds (as precisely as you can judge from the
  audio)
- speaker: a label like "Speaker 1" if you can distinguish voices,
  otherwise leave it empty
- dialogue: the verbatim words spoken, or empty if this segment has no
  speech
- events: short non-verbal audio cues in this segment, if any (e.g.
  ["music starts"], ["door slams"]) — leave empty if none

Segments should be short — a single line of dialogue or a single audio
event each. Do not group multiple exchanges into one segment. Cover the
entire audio duration; do not stop early.
"""


def transcribe_audio(
    audio_path: str,
    llm: LLMClient,
    cache_key: str | None = None,
    model: str | None = None,
) -> list[AudioEvent]:
    """Return fine-grained, timestamped segments ready for build_shot_records()."""
    transcript = llm.generate_structured(
        system_prompt=TRANSCRIPT_PROMPT,
        media=audio_path,
        context={},
        response_schema=AudioTranscript,
        cache_key=f"{cache_key}-transcript" if cache_key else None,
        model=model,
    )
    return [
        AudioEvent(
            start=segment.start,
            end=segment.end,
            dialogue=segment.dialogue,
            events=segment.events,
        )
        for segment in transcript.segments
    ]