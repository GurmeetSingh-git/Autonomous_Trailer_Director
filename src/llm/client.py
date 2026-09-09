# src/llm/client.py
import json
import os
from pathlib import Path
from typing import Any, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, mode: str = "replay", replay_dir: Path | None = None):
        self.mode = mode
        self.replay_dir = replay_dir or Path("sample_run/replay_cache")

    def generate_structured(
        self,
        system_prompt: str,
        media: str | None,
        context: dict[str, Any],
        response_schema: Type[T],
        cache_key: str | None = None,
    ) -> T:
        if self.mode == "replay":
            return self._load_replay(cache_key or context.get("scene_id", "unknown"), response_schema)
        return self._call_live(system_prompt, media, context, response_schema)

    def _load_replay(self, cache_key: str, response_schema: Type[T]) -> T:
        path = self.replay_dir / f"{cache_key}.json"
        if not path.exists():
            raise FileNotFoundError(f"No replay fixture for '{cache_key}' at {path}")
        data = json.loads(path.read_text())
        return response_schema.model_validate(data)

    def _call_live(self, system_prompt, media, context, response_schema: Type[T]) -> T:
        # Wire up google-genai here. Raise clearly if GEMINI_API_KEY is missing
        # rather than failing deep inside a genai call.
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set; use mode='replay' or set the key.")
        raise NotImplementedError("Wire up google-genai call here")