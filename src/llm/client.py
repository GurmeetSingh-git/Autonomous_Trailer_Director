# src/llm/client.py
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


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
        model: str | None = None,
    ) -> T:
        if self.mode == "replay":
            return self._load_replay(cache_key or context.get("scene_id", "unknown"), response_schema)
        return self._call_live(system_prompt, media, context, response_schema, model)

    def _load_replay(self, cache_key: str, response_schema: Type[T]) -> T:
        path = self.replay_dir / f"{cache_key}.json"
        if not path.exists():
            raise FileNotFoundError(f"No replay fixture for '{cache_key}' at {path}")
        data = json.loads(path.read_text())
        return response_schema.model_validate(data)

    def _call_live(self, system_prompt, media, context, response_schema: Type[T], model: str | None = None) -> T:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set; add it to .env before uploading a video.")
        if not media:
            raise ValueError("A video path is required for live media analysis.")

        client = genai.Client(api_key=api_key)
        uploaded = client.files.upload(file=media)
        logger.info("Uploading media file to Gemini: %s", Path(media).name)
        for _ in range(60):
            state = getattr(uploaded, "state", None)
            state_name = getattr(state, "name", state)
            logger.debug("Gemini media state for %s: %s", Path(media).name, state_name)
            if state_name in (None, "ACTIVE"):
                break
            if state_name == "FAILED":
                error = getattr(state, "error", None)
                detail = getattr(error, "message", None) or str(error or "unknown processing error")
                raise RuntimeError(f"Gemini could not process the uploaded video: {detail}")
            time.sleep(2)
            uploaded = client.files.get(name=uploaded.name)
        else:
            raise TimeoutError("Timed out while Gemini processed the uploaded video.")

        prompt = f"{system_prompt}\n\nContext:\n{json.dumps(context, default=str)}"
        selected_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        logger.info("Generating structured Gemini response with model %s", selected_model)
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=selected_model,
                    contents=[uploaded, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema,
                    ),
                )
                break
            except Exception as exc:
                if "503" not in str(exc) or attempt == 2:
                    raise
                delay = 5 * (attempt + 1)
                logger.warning("Gemini is temporarily unavailable; retrying in %s seconds", delay)
                time.sleep(delay)
        if getattr(response, "parsed", None) is not None:
            logger.info("Gemini returned a parsed structured response")
            return response.parsed
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response_schema.model_validate_json(response.text)