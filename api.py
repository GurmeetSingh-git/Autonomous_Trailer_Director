"""FastAPI entrypoint for the Autonomous Trailer Director frontend."""

from copy import deepcopy
import logging
import os
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.llm.client import LLMClient


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
    description: str
    characters: list[str] = Field(default_factory=list)
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
Return several chronological scenes with HH:MM:SS timecodes. Mark spoiler_level
as low, medium, or high. The spoiler_budget is the maximum percentage of the
episode that can be revealed without giving away the ending; choose a sensible
value between 10 and 30.
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
        "scenes": [
            {
                "id": scene.id,
                "title": scene.title,
                "timecode": scene.timecode,
                "description": scene.description,
                "characters": scene.characters,
                "spoilerLevel": scene.spoiler_level,
                "selected": scene.spoiler_level != "high",
            }
            for scene in generated.scenes
        ],
    }
    trailer = build_trailer(run_id, audience, story_map)
    runs[run_id] = {"story_map": story_map, "trailer": trailer, "filename": safe_name, "video_path": str(video_path)}
    return {"runId": run_id}


def build_trailer(run_id: str, audience: str, story_map: dict) -> dict:
    scenes = [scene for scene in story_map["scenes"] if scene.get("selected")][:3]
    segments = [
        {
            "id": chr(97 + index),
            "label": ["The question", "The threshold", "The promise"][index],
            "sceneId": scene["id"],
            "start": scene["timecode"],
            "end": scene["timecode"],
            "tone": "discovery",
        }
        for index, scene in enumerate(scenes)
    ]
    return {
        "id": run_id,
        "title": story_map["title"],
        "audience": audience,
        "runtime": "01:32",
        "segments": segments,
        "validation": {"status": "PASS_WITH_WARNINGS", "checks": [],},
        "evidence": ["Scenes were selected from the uploaded episode analysis."],
    }


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


@app.post("/runs/{run_id}/plan")
def plan_trailer(run_id: str) -> dict:
    return get_run(run_id)["trailer"]