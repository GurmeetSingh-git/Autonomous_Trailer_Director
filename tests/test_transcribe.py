import wave
from pathlib import Path
from types import SimpleNamespace

from src.ingestion import transcribe


def test_transcribe_audio_offsets_and_keys_long_audio_chunks(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "episode.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(10)
        audio.writeframes(b"\0\0" * 25)

    monkeypatch.setattr(transcribe, "TRANSCRIPT_CHUNK_SECONDS", 1)
    calls = []

    class FakeLLM:
        def generate_structured(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(segments=[
                SimpleNamespace(start=0.2, end=0.8, dialogue="line", events=[]),
            ])

    events = transcribe.transcribe_audio(str(audio_path), FakeLLM(), cache_key="run-1")

    assert [event["start"] for event in events] == [0.2, 1.2, 2.2]
    assert [event["end"] for event in events] == [0.8, 1.8, 2.8]
    assert [call["cache_key"] for call in calls] == [
        "run-1-transcript-chunk-0000",
        "run-1-transcript-chunk-0001",
        "run-1-transcript-chunk-0002",
    ]
    assert [call["context"]["time_offset_seconds"] for call in calls] == [0, 1, 2]
    assert "begins at 2.0 seconds" in calls[2]["system_prompt"]


def test_transcribe_audio_keeps_short_audio_as_single_request(tmp_path: Path) -> None:
    audio_path = tmp_path / "short.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(10)
        audio.writeframes(b"\0\0" * 5)

    calls = []

    class FakeLLM:
        def generate_structured(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(segments=[
                SimpleNamespace(start=0.0, end=0.4, dialogue="hello", events=[]),
            ])

    events = transcribe.transcribe_audio(str(audio_path), FakeLLM(), cache_key="run-2")

    assert events[0]["dialogue"] == "hello"
    assert len(calls) == 1
    assert calls[0]["cache_key"] == "run-2-transcript"
