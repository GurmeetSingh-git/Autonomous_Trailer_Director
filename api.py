"""FastAPI entrypoint for the Autonomous Trailer Director frontend."""

from copy import deepcopy
import logging
import os
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.llm.client import LLMClient
from src.models.story_map import StoryMap
from src.constraints.constraint_engine import ConstraintEngine
from src.logging.decision_log import DecisionLog
from src.orchestration.pipeline import AUDIENCES, build_plan


load_dotenv()
logger = logging.getLogger(__name__)


app = FastAPI(title="Autonomous Trailer Director")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEMO_STORY_MAP = {
    "title": "The Last Light",
    "logline": "When an apprentice cartographer discovers a vanished city on an impossible map, she must choose between the life she knows and the world hiding in plain sight.",
    "spoilerBudget": 22,
    "characters": [
        {"name": "Mara Venn", "role": "The cartographer", "color": "coral"},
        {"name": "Ilan", "role": "Her brother", "color": "sky"},
        {"name": "The Keeper", "role": "A hidden guide", "color": "gold"},
    ],
    "scenes": [
        {"id": "s01", "title": "The impossible coastline", "timecode": "00:04:12", "description": "Mara finds a coastline that does not exist in any atlas.", "characters": ["Mara Venn"], "spoilerLevel": "low", "selected": True},
        {"id": "s07", "title": "A door in the archive", "timecode": "00:18:44", "description": "A midnight key reveals a door behind the city archive.", "characters": ["Mara Venn", "Ilan"], "spoilerLevel": "low", "selected": True},
        {"id": "s13", "title": "The first crossing", "timecode": "00:39:08", "description": "The siblings step into a city lit by a second moon.", "characters": ["Mara Venn", "Ilan", "The Keeper"], "spoilerLevel": "medium", "selected": True},
        {"id": "s18", "title": "The choice", "timecode": "00:54:27", "description": "Mara learns what the map was made to protect.", "characters": ["Mara Venn", "The Keeper"], "spoilerLevel": "high"},
    ],
}

DEMO_TRAILER = {
    "id": "demo-run",
    "title": "The Last Light",
    "audience": "family",
    "runtime": "01:32",
    "segments": [
        {"id": "a", "label": "The question", "sceneId": "s01", "start": "00:04:12", "end": "00:04:35", "tone": "wonder"},
        {"id": "b", "label": "The threshold", "sceneId": "s07", "start": "00:18:44", "end": "00:19:20", "tone": "discovery"},
        {"id": "c", "label": "The promise", "sceneId": "s13", "start": "00:39:08", "end": "00:39:51", "tone": "adventure"},
    ],
    "validation": {
        "status": "PASS_WITH_WARNINGS",
        "checks": [
            {"name": "Existence", "status": "pass", "detail": "3 of 3 source clips found"},
            {"name": "Spoiler budget", "status": "pass", "detail": "18 / 22 points used"},
            {"name": "Rights", "status": "pass", "detail": "All assets cleared"},
            {"name": "Accessibility", "status": "warning", "detail": "Audio description still pending"},
            {"name": "Rating", "status": "pass", "detail": "Suitable for family audience"},
        ],
    },
    "evidence": [
        "Opening establishes the mystery in under 5 seconds.",
        "The threshold scene pays off the audience promise without revealing the final act.",
        "Dialogue density stays below the family-audience threshold.",
    ],
}

runs: dict[str, dict] = {}
UPLOAD_DIR = Path("runtime/uploads")


class StoryCharacter(BaseModel):
    name: str
    role: str


class StoryScene(BaseModel):
    id: str
    title: str
    timecode: str
    end_timecode: str | None = None
    content_start_timecode: str | None = None
    content_end_timecode: str | None = None
    description: str
    characters: list[str] = Field(default_factory=list)
    emotion: str = ""
    tone: str = ""
    sensitive_content: list[str] = Field(default_factory=list)
    spoiler_level: str = "low"


class GeneratedStoryMap(BaseModel):
    title: str
    logline: str
    characters: list[StoryCharacter] = Field(default_factory=list)
    scenes: list[StoryScene] = Field(default_factory=list)
    spoiler_budget: int = 22


STORY_MAP_PROMPT = """
Analyze the uploaded episode video and produce a spoiler-aware story map.
Use only events, characters, and dialogue visible or audible in the video.
Keep scene descriptions concise and do not invent names when they are unknown.
Break the episode into 4 to 8 distinct chronological story beats whenever the
video supports them; do not merge the whole episode into only one or two broad
scenes. Return each beat with start timecode and end_timecode in HH:MM:SS format.
Also return content_start_timecode and content_end_timecode for the shortest
self-contained trailer-worthy beat in that scene, normally 10 to 15 seconds.
These content timecodes must be inside the scene boundaries and grounded in
visible action or spoken dialogue; do not choose them by duration alone. Mark spoiler_level
as low, medium, or high. The spoiler_budget is the maximum percentage of the
episode that can be revealed without giving away the ending; choose a sensible
value between 10 and 30.
Also classify each beat with an emotion and concise tone such as wonder,
tension, stakes, humour, discovery, or calm.
"""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs")
async def create_run(
    episode: UploadFile = File(...),
    audience: str = Form("family"),
    model: str = Form(""),
) -> dict[str, str]:
    run_id = str(uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(episode.filename or "episode.mp4").name
    video_path = UPLOAD_DIR / f"{run_id}_{safe_name}"
    with video_path.open("wb") as destination:
        shutil.copyfileobj(episode.file, destination)
    logger.info("Saved uploaded episode %s (%d bytes)", safe_name, video_path.stat().st_size)
    selected_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not selected_model.startswith("gemini-"):
        video_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid Gemini model selection.")

    try:
        llm = LLMClient(mode="live")
        generated = llm.generate_structured(
            system_prompt=STORY_MAP_PROMPT,
            media=str(video_path),
            context={"audience": audience, "filename": safe_name},
            response_schema=GeneratedStoryMap,
            cache_key=run_id,
            model=selected_model,
        )
        logger.info("Gemini raw scenes: %s", [scene.model_dump() for scene in generated.scenes])
    except Exception as exc:
        video_path.unlink(missing_ok=True)
        logger.exception("Episode analysis failed for run %s", run_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    story_map = {
        "title": generated.title,
        "logline": generated.logline,
        "spoilerBudget": generated.spoiler_budget,
        "characters": [
            {"name": character.name, "role": character.role, "color": color}
            for color, character in zip(("coral", "sky", "gold"), generated.characters)
        ],
        "scenes": normalize_scenes(generated.scenes, video_path),
    }
    internal_story_map = {
        **story_map,
        "spoiler_budget": story_map["spoilerBudget"],
        "characters": [character["name"] for character in story_map["characters"]],
        "scenes": [
            {
                **scene,
                "spoiler_level": scene["spoilerLevel"],
                "dialogue": True,
                "trailer_start": scene.get("trailerStart", scene["start"]),
                "trailer_end": scene.get("trailerEnd", scene["end"]),
                "emotion": scene.get("emotion", ""),
                "tone": scene.get("tone", ""),
                "sensitive_content": scene.get("sensitiveContent", []),
            }
            for scene in story_map["scenes"]
        ],
    }
    constraint_map = ConstraintEngine().build(StoryMap.model_validate(internal_story_map)).model_dump()
    log = DecisionLog()
    plans = {name: build_plan(name, internal_story_map, constraint_map, log) for name in AUDIENCES}
    selected_audience = audience if audience in AUDIENCES else "family"
    trailer = trailer_from_plan(run_id, plans[selected_audience], story_map["title"])
    runs[run_id] = {
        "story_map": story_map,
        "trailer": trailer,
        "plans": plans,
        "constraint_map": constraint_map,
        "decision_log": log.as_list(),
        "filename": safe_name,
        "video_path": str(video_path),
    }
    return {"runId": run_id}


def parse_timecode(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_timecode(value: float) -> str:
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"


def media_duration(path: Path) -> float | None:
    try:
        import cv2
        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS)
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        capture.release()
        return frames / fps if fps and frames else None
    except Exception:
        return None


def normalize_scenes(scenes: list[StoryScene], video_path: Path) -> list[dict]:
    """Normalize scene and content timestamps, preventing invalid edit ranges."""
    duration = media_duration(video_path)
    starts = [parse_timecode(scene.timecode) for scene in scenes]
    if scenes and duration and not any(starts):
        interval = duration / len(scenes)
        starts = [index * interval for index in range(len(scenes))]
    normalized = []
    for index, scene in enumerate(scenes):
        start = starts[index]
        end = parse_timecode(scene.end_timecode) if scene.end_timecode else (starts[index + 1] if index + 1 < len(starts) else start + 30)
        if end <= start:
            end = starts[index + 1] if index + 1 < len(starts) and starts[index + 1] > start else start + 30
        content_start = parse_timecode(scene.content_start_timecode) if scene.content_start_timecode else start
        content_end = parse_timecode(scene.content_end_timecode) if scene.content_end_timecode else min(end, content_start + 15)
        content_start = max(start, min(content_start, end))
        content_end = max(content_start, min(content_end, end))
        if content_end <= content_start:
            content_start, content_end = start, min(end, start + 15)
        normalized.append({
            "id": scene.id,
            "title": scene.title,
            "timecode": format_timecode(start),
            "endTimecode": format_timecode(end),
            "start": start,
            "end": end,
            "trailerStart": content_start,
            "trailerEnd": content_end,
            "description": scene.description,
            "characters": scene.characters,
            "emotion": scene.emotion,
            "tone": scene.tone,
            "sensitiveContent": scene.sensitive_content,
            "spoilerLevel": scene.spoiler_level,
            "selected": scene.spoiler_level != "high",
        })
    return normalized


def trailer_from_plan(run_id: str, plan: dict, title: str) -> dict:
    return {
        "id": run_id,
        "title": title,
        "audience": plan["audience"],
        "runtime": format_timecode(plan["duration_seconds"]),
        "segments": [
            {
                "id": chr(97 + index),
                "label": segment["video"],
                "sceneId": segment["scene_id"],
                "start": format_timecode(segment["start"]),
                "end": format_timecode(segment["end"]),
                "tone": segment.get("tone", "discovery"),
            }
            for index, segment in enumerate(plan["segments"])
        ],
        "validation": {
            "status": plan["validation"]["status"],
            "checks": [
                {"name": check["name"], "status": check["status"], "detail": check["detail"]}
                for check in plan["validation"]["checks"]
            ],
        },
        "evidence": [evidence for segment in plan["segments"] for evidence in segment["evidence"]],
    }


@app.get("/runs/{run_id}/media")
def get_media(run_id: str) -> FileResponse:
    run = get_run(run_id)
    media_path = Path(run.get("video_path", ""))
    if not media_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded media is no longer available")
    return FileResponse(media_path)


def get_run(run_id: str) -> dict:
    if run_id == "demo-run":
        return {"story_map": deepcopy(DEMO_STORY_MAP), "trailer": deepcopy(DEMO_TRAILER)}
    try:
        return runs[run_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/runs/{run_id}/story-map")
def get_story_map(run_id: str) -> dict:
    return get_run(run_id)["story_map"]


@app.get("/runs/{run_id}/trailer")
def get_trailer(run_id: str) -> dict:
    return get_run(run_id)["trailer"]


@app.get("/runs/{run_id}/plans")
def get_plans(run_id: str) -> dict:
    run = get_run(run_id)
    return {"plans": run.get("plans", {}), "constraintMap": run.get("constraint_map", {}), "decisionLog": run.get("decision_log", [])}


@app.post("/runs/{run_id}/plan")
def plan_trailer(run_id: str) -> dict:
    return get_run(run_id)["trailer"]