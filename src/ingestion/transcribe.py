"""Run this BEFORE the narrative STORY_MAP_PROMPT call, on the same
extracted audio file. It replaces "summarize the audio" with "transcribe
the audio" as a distinct job, which is what gives build_shot_records()
something fine-grained enough to actually attach to 32 shots instead of 5
broad scenes.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from src.ingestion.shot_records import AudioEvent
from src.llm.client import LLMClient
from src.models.transcript import AudioTranscript

TRANSCRIPT_CHUNK_SECONDS = 180

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


def _transcribe_chunk(
    audio_path: str,
    llm: LLMClient,
    cache_key: str | None,
    model: str | None,
    time_offset: float = 0.0,
) -> list[AudioEvent]:
    prompt = TRANSCRIPT_PROMPT
    if time_offset:
        prompt += (
            f"\n\nThis chunk begins at {time_offset:.1f} seconds in the full episode. "
            "Return timestamps relative to the beginning of this chunk."
        )
    transcript = llm.generate_structured(
        system_prompt=prompt,
        media=audio_path,
        context={"time_offset_seconds": time_offset},
        response_schema=AudioTranscript,
        cache_key=cache_key,
        model=model,
    )
    return [
        AudioEvent(
            start=segment.start + time_offset,
            end=segment.end + time_offset,
            dialogue=segment.dialogue,
            events=segment.events,
        )
        for segment in transcript.segments
    ]


def transcribe_audio(
    audio_path: str,
    llm: LLMClient,
    cache_key: str | None = None,
    model: str | None = None,
) -> list[AudioEvent]:
    """Return timestamped transcript segments, splitting long audio to bound model output."""
    with wave.open(audio_path, "rb") as source:
        params = source.getparams()
        chunk_frames = params.framerate * TRANSCRIPT_CHUNK_SECONDS
        if params.nframes <= chunk_frames:
            return _transcribe_chunk(
                audio_path,
                llm,
                f"{cache_key}-transcript" if cache_key else None,
                model,
            )
        if params.comptype != "NONE":
            raise ValueError(f"Unsupported audio compression for transcription: {params.comptype}")

        all_events: list[AudioEvent] = []
        with tempfile.TemporaryDirectory(prefix="episode-transcript-") as temp_dir:
            chunk_index = 0
            while True:
                frames = source.readframes(chunk_frames)
                if not frames:
                    break
                chunk_path = Path(temp_dir) / f"chunk-{chunk_index:04d}.wav"
                with wave.open(str(chunk_path), "wb") as chunk:
                    chunk.setparams(params)
                    chunk.writeframes(frames)

                time_offset = chunk_index * TRANSCRIPT_CHUNK_SECONDS
                chunk_key = (
                    f"{cache_key}-transcript-chunk-{chunk_index:04d}"
                    if cache_key
                    else None
                )
                all_events.extend(
                    _transcribe_chunk(
                        str(chunk_path), llm, chunk_key, model, time_offset
                    )
                )
                chunk_index += 1

    return all_events