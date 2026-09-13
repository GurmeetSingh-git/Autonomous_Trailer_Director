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


def _is_retryable_api_error(error: Exception) -> bool:
    """Recognize transient Gemini availability and rate-limit responses."""
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    detail = str(error).upper()
    return (
        status_code in {429, 500, 502, 503, 504}
        or any(marker in detail for marker in (
            "429", "RESOURCE_EXHAUSTED", "RATE LIMIT", "RATE_LIMIT", "QUOTA",
            "503", "500", "502", "504",
        ))
    )


def _retry_delay(error: Exception, attempt: int) -> float:
    """Use a bounded exponential backoff for transient API failures."""
    retry_after = getattr(error, "retry_after", None)
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        return min(float(retry_after), 60.0)
    return min(5.0 * (2 ** attempt), 60.0)


class LLMClient:
    def __init__(self, mode: str = "replay", replay_dir: Path | None = None):
        self.mode = mode
        self.replay_dir = replay_dir or Path("sample_run/replay_cache")

    def generate_structured(
            self,
            system_prompt: str,
            media: str | list[str] | None,     # <-- was: str | None
            context: dict,
            response_schema,
            cache_key: str | None = None,
            model: str | None = None,
        ):
            if self.mode == "replay":
                return self._load_replay(cache_key or context.get("scene_id", "unknown"), response_schema)
            return self._call_live(system_prompt, media, context, response_schema, model)

    def _load_replay(self, cache_key: str, response_schema: Type[T]) -> T:
        path = self.replay_dir / f"{cache_key}.json"
        if not path.exists():
            raise FileNotFoundError(f"No replay fixture for '{cache_key}' at {path}")
        data = json.loads(path.read_text())
        return response_schema.model_validate(data)

    def _call_live(self, system_prompt, media, context, response_schema, model: str | None = None):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set; add it to .env before uploading a video.")

        media_paths = [media] if isinstance(media, str) else list(media or [])
 
        client = genai.Client(api_key=api_key)
        uploaded_files = []
        for media_path in media_paths:
            for attempt in range(3):
                try:
                    uploaded = client.files.upload(file=media_path)
                    break
                except Exception as exc:
                    if not _is_retryable_api_error(exc) or attempt == 2:
                        raise
                    delay = _retry_delay(exc, attempt)
                    logger.warning(
                        "Gemini media upload was rate-limited or unavailable; retrying in %.1f seconds",
                        delay,
                    )
                    time.sleep(delay)
            logger.info("Uploading media file to Gemini: %s", Path(media_path).name)
            for _ in range(60):
                state = getattr(uploaded, "state", None)
                state_name = getattr(state, "name", state)
                logger.debug("Gemini media state for %s: %s", Path(media_path).name, state_name)
                if state_name in (None, "ACTIVE"):
                    break
                if state_name == "FAILED":
                    error = getattr(state, "error", None)
                    detail = getattr(error, "message", None) or str(error or "unknown processing error")
                    raise RuntimeError(f"Gemini could not process the uploaded media: {detail}")
                time.sleep(2)
                uploaded = client.files.get(name=uploaded.name)
            else:
                raise TimeoutError("Timed out while Gemini processed the uploaded media.")
            uploaded_files.append(uploaded)
 
        prompt = f"{system_prompt}\n\nContext:\n{json.dumps(context, default=str)}"
        selected_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        logger.info(
            "Generating structured Gemini response with model %s over %d file(s)",
            selected_model, len(uploaded_files),
        )
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=selected_model,
                    contents=[*uploaded_files, prompt],   # <-- was: [uploaded, prompt]
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=response_schema,
                    ),
                )
                break
            except Exception as exc:
                if not _is_retryable_api_error(exc) or attempt == 2:
                    raise
                delay = _retry_delay(exc, attempt)
                logger.warning(
                    "Gemini request was rate-limited or unavailable; retrying in %.1f seconds",
                    delay,
                )
                time.sleep(delay)
        if getattr(response, "parsed", None) is not None:
            logger.info("Gemini returned a parsed structured response")
            return response.parsed
        if not response.text:
            raise RuntimeError("Gemini returned an empty response.")
        return response_schema.model_validate_json(response.text)