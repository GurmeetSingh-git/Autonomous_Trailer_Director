"""FastAPI entrypoint for the Autonomous Trailer Director frontend."""

from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
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
from src.planning.audience_strategy import AUDIENCE_GOALS
from src.verification.validator import Validator


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
RENDER_DIR = Path("runtime/renders")
RUNS_FILE = Path("runtime/runs.json")
AUDIENCE_ARC_CACHE_VERSION = 4

if RUNS_FILE.is_file():
    try:
        runs.update(json.loads(RUNS_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not restore saved run state from %s", RUNS_FILE)


def save_runs() -> None:
    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = RUNS_FILE.with_suffix(".tmp")
    temporary_file.write_text(json.dumps(runs), encoding="utf-8")
    temporary_file.replace(RUNS_FILE)


def planning_story_map(run: dict) -> dict:
    """Return the normalized story map used by the audience planner."""
    if "planning_story_map" in run:
        return run["planning_story_map"]
    story_map = run["story_map"]
    return {
        **story_map,
        "spoiler_budget": story_map.get("spoilerBudget", 22),
        "scenes": [
            {
                **scene,
                "spoiler_level": scene.get("spoilerLevel", "low"),
                "dialogue": True,
                "trailer_start": scene.get("trailerStart", scene.get("start", 0)),
                "trailer_end": scene.get("trailerEnd", scene.get("end", 0)),
                "sensitive_content": scene.get("sensitiveContent", []),
            }
            for scene in story_map.get("scenes", [])
        ],
    }


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


class PromiseBeat(BaseModel):
    scene_id: str
    beat_name: str
    source_in: str
    source_out: str
    emotional_goal: str
    included: bool = True


class PromiseArcUpdate(BaseModel):
    audience: str = "family"
    audience_profile: str = ""
    audience_promise: str
    narrative_arc: list[PromiseBeat]


class AudienceCandidate(BaseModel):
    scene_id: str
    source_in: str
    source_out: str
    emotional_goal: str


class AudienceCandidates(BaseModel):
    candidates: list[AudienceCandidate] = Field(default_factory=list)


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


def save_supporting_upload(upload: UploadFile | None, run_id: str, label: str) -> dict[str, str] | None:
    if upload is None:
        return None
    safe_name = Path(upload.filename or f"{label}.bin").name
    path = UPLOAD_DIR / f"{run_id}_{label}_{safe_name}"
    with path.open("wb") as destination:
        shutil.copyfileobj(upload.file, destination)
    result = {"filename": safe_name, "path": str(path)}
    if path.suffix.lower() in {".json", ".txt", ".csv", ".srt", ".vtt"}:
        result["content"] = path.read_text(encoding="utf-8", errors="replace")[:20000]
    return result


@app.post("/runs")
async def create_run(
    episode: UploadFile = File(...),
    audience: str = Form("family"),
    model: str = Form(""),
    scene_descriptions: UploadFile | None = File(None),
    dialogue_subtitles: UploadFile | None = File(None),
    policies_metadata: UploadFile | None = File(None),
) -> dict[str, str]:
    run_id = str(uuid4())
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(episode.filename or "episode.mp4").name
    video_path = UPLOAD_DIR / f"{run_id}_{safe_name}"
    with video_path.open("wb") as destination:
        shutil.copyfileobj(episode.file, destination)
    logger.info("Saved uploaded episode %s (%d bytes)", safe_name, video_path.stat().st_size)
    supporting_files = {
        "scene_descriptions": save_supporting_upload(scene_descriptions, run_id, "scenes"),
        "dialogue_subtitles": save_supporting_upload(dialogue_subtitles, run_id, "dialogue"),
        "policies_metadata": save_supporting_upload(policies_metadata, run_id, "policies"),
    }
    evidence_context = {
        key: {field: value for field, value in (item or {}).items() if field != "path"}
        for key, item in supporting_files.items()
        if item
    }
    selected_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not selected_model.startswith("gemini-"):
        video_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid Gemini model selection.")

    try:
        llm = LLMClient(mode="live")
        generated = llm.generate_structured(
            system_prompt=STORY_MAP_PROMPT,
            media=str(video_path),
            context={"audience": audience, "filename": safe_name, "supporting_evidence": evidence_context},
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
        "planning_story_map": internal_story_map,
        "promise_arc": promise_arc_from_plan(plans[selected_audience]),
        "constraint_map": constraint_map,
        "decision_log": log.as_list(),
        "filename": safe_name,
        "video_path": str(video_path),
        "supporting_files": supporting_files,
    }
    save_runs()
    return {"runId": run_id}


def parse_timecode(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def format_timecode(value: float) -> str:
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"


def format_editable_timecode(value: float) -> str:
    """Keep sub-second precision when a timecode will be submitted again."""
    hours, remainder = divmod(value, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:05.2f}"


def reanalyze_audience_plan(run_id: str, run: dict, audience: str) -> dict:
    """Ask the media model for fresh, audience-grounded source moments."""
    story_map = planning_story_map(run)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    context = {
        "audience": audience,
        "audience_goal": AUDIENCE_GOALS[audience],
        "scenes": [{key: scene.get(key) for key in ("id", "start", "end", "description", "emotion", "tone", "characters", "spoiler_level")} for scene in story_map["scenes"]],
    }
    prompt = """
Review the uploaded video again for the requested audience. Select up to three
non-spoiler moments that best serve the audience goal. Return only moments
that visibly or audibly occur in the video and inside the supplied scene
boundaries. Use precise HH:MM:SS.ss timecodes. Prefer different moments when
the audience goal calls for a different emphasis. Explain why each moment
serves the audience in emotional_goal.
"""
    result = LLMClient(mode="live").generate_structured(
        system_prompt=prompt,
        media=run["video_path"],
        context=context,
        response_schema=AudienceCandidates,
        cache_key=f"{run_id}-{audience}",
        model=model,
    )
    scenes = {scene["id"]: scene for scene in story_map["scenes"]}
    segments = []
    for candidate in result.candidates[:3]:
        scene = scenes.get(candidate.scene_id)
        if not scene:
            continue
        start = parse_timecode(candidate.source_in)
        end = parse_timecode(candidate.source_out)
        if scene["spoiler_level"] == "high" or start < scene["start"] or end > scene["end"] or end <= start:
            continue
        segments.append({
            "source_in": start, "source_out": end, "video": scene["id"], "audio": "original_dialogue",
            "subtitle": "source_subtitles", "tone": scene.get("tone") or "discovery", "sensitive_content": scene.get("sensitive_content", []),
            "reason": candidate.emotional_goal, "evidence": [f"scene:{scene['id']}", "human:audience_reanalysis"], "risk_flags": [],
            "scene_id": scene["id"], "start": start, "end": end, "spoiler_level": scene["spoiler_level"],
        })
    if not segments:
        raise ValueError("The model returned no valid audience-grounded moments.")
    segments.sort(key=lambda item: item["start"])
    validation = Validator().validate(segments, {
        "scene_ids": run["constraint_map"].get("metadata", {}).get("scene_ids", []),
        "cleared_scene_ids": run["constraint_map"].get("metadata", {}).get("cleared_scene_ids", []),
        "expired_assets": run["constraint_map"].get("metadata", {}).get("expired_assets", []),
        "protected_facts": run["constraint_map"].get("metadata", {}).get("protected_facts", []),
        "audience": audience, "estimated_cost_usd": 0.02,
        "max_cost_usd": run["constraint_map"].get("metadata", {}).get("max_cost_usd", 1.0),
    })
    plan = build_plan(audience, story_map, run["constraint_map"], DecisionLog())
    plan.update({"segments": segments, "duration_seconds": sum(item["end"] - item["start"] for item in segments), "validation": validation})
    return plan


def promise_arc_from_plan(plan: dict) -> dict:
    """Expose the intent that precedes clip selection in an editable form."""
    beat_names = ("Introduction / Setup", "Conflict / Turning Point", "Resolution / Core Message")
    return {
        "audience": plan["audience"],
        "audience_profile": plan["audience"],
        "audience_promise": plan["audience_promise"],
        "narrative_arc": [
            {
                "scene_id": segment["scene_id"],
                "beat_name": beat_names[index] if index < len(beat_names) else f"Story beat {index + 1}",
                "source_in": format_editable_timecode(segment["start"]),
                "source_out": format_editable_timecode(segment["end"]),
                "emotional_goal": segment["reason"],
                "included": True,
            }
            for index, segment in enumerate(plan["segments"])
        ],
        "validation_status": plan["validation"]["status"],
    }


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
    validation = plan["validation"]
    validation_status = validation["status"]
    if validation_status == "PASS" and any(check.get("status") == "warning" for check in validation.get("checks", [])):
        validation_status = "PASS_WITH_WARNINGS"
    if any(check.get("status") == "fail" for check in validation.get("checks", [])):
        validation_status = "REJECT"
    contract_link = "contract:pending-human-clearance"
    return {
        "id": run_id,
        "trailer_id": plan.get("trailer_id", run_id),
        "title": title,
        "audience": plan["audience"],
        "runtime": format_timecode(plan["duration_seconds"]),
        "duration_seconds": plan["duration_seconds"],
        "audience_promise": plan.get("audience_promise", ""),
        "segments": [
            {
                "id": chr(97 + index),
                "label": segment.get("label", segment["video"]),
                "scene_id": segment["scene_id"],
                "sceneId": segment["scene_id"],
                "source_in": format_timecode(segment["source_in"]),
                "source_out": format_timecode(segment["source_out"]),
                "start": format_timecode(segment["start"]),
                "end": format_timecode(segment["end"]),
                "tone": segment.get("tone", "discovery"),
                "audio": segment.get("audio", "original_dialogue"),
                "subtitle": segment.get("subtitle", "source_subtitles"),
                "reason": segment.get("reason", ""),
                "evidence": list(dict.fromkeys([*segment.get("evidence", []), contract_link])),
                "risk_flags": segment.get("risk_flags", []),
                "validation": {
                    "status": validation_status,
                    "checks": validation.get("checks", []),
                },
                "is_included": segment.get("is_included", True),
            }
            for index, segment in enumerate(plan["segments"])
        ],
        "validation": {
            "status": validation_status,
            "checks": [
                {"name": check["name"], "status": check["status"], "detail": check["detail"]}
                for check in validation["checks"]
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


def render_segments(run_id: str, run: dict) -> Path:
    """Slice the validated EDL and concatenate the clips into one video."""
    media_path = Path(run.get("video_path", ""))
    if not media_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded media is no longer available")
    segments = run.get("trailer", {}).get("segments", [])
    if not segments:
        raise HTTPException(status_code=422, detail="The validated timeline has no included clips")
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RENDER_DIR / f"{run_id}.mp4"
    inputs = []
    filters = []
    for index, segment in enumerate(segments):
        start = parse_timecode(segment["start"])
        end = parse_timecode(segment["end"])
        inputs.extend(["-ss", str(start), "-t", str(end - start), "-i", str(media_path)])
        filters.append(f"[{index}:v]setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[{index}:a]aresample=async=1:first_pts=0[a{index}]")
    video_inputs = "".join(f"[v{index}][a{index}]" for index in range(len(segments)))
    filters.append(f"{video_inputs}concat=n={len(segments)}:v=1:a=1[vout][aout]")
    ffmpeg_executable = shutil.which("ffmpeg")
    if not ffmpeg_executable:
        winget_root = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        matches = list(winget_root.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"))
        ffmpeg_executable = str(matches[0]) if matches else "ffmpeg"
    command = [ffmpeg_executable, "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(output_path)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        return render_segments_with_opencv(segments, media_path, output_path)
    except subprocess.CalledProcessError as exc:
        detail = "FFmpeg is required to render the final trailer."
        if exc.stderr:
            logger.error("Trailer render failed: %s", exc.stderr[-2000:])
            detail = "The final trailer could not be rendered. Check the uploaded media and FFmpeg installation."
        raise HTTPException(status_code=503, detail=detail) from exc
    return output_path


def render_segments_with_opencv(segments: list[dict], media_path: Path, output_path: Path) -> Path:
    """Fallback renderer for local setups without an FFmpeg executable."""
    try:
        import cv2
        capture = cv2.VideoCapture(str(media_path))
        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not capture.isOpened() or not writer.isOpened():
            raise RuntimeError("Unable to open source or output video")
        for segment in segments:
            start_frame = max(0, int(parse_timecode(segment["start"]) * fps))
            end_frame = max(start_frame, int(parse_timecode(segment["end"]) * fps))
            capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            for _ in range(start_frame, end_frame):
                success, frame = capture.read()
                if not success:
                    break
                writer.write(frame)
        capture.release()
        writer.release()
    except (ImportError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=503, detail="The trailer could not be rendered with FFmpeg or OpenCV.") from exc
    return output_path


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


@app.get("/runs/{run_id}/promise-arc")
def get_promise_arc(run_id: str, audience: str | None = None) -> dict:
    run = get_run(run_id)
    if audience:
        if audience not in AUDIENCES:
            raise HTTPException(status_code=400, detail="Unsupported audience.")
        if run.get("audience_arc_cache_version") != AUDIENCE_ARC_CACHE_VERSION:
            run["audience_arc_cache"] = {}
            run["audience_arc_cache_version"] = AUDIENCE_ARC_CACHE_VERSION
        arc_cache = run.setdefault("audience_arc_cache", {})
        if audience in arc_cache:
            return arc_cache[audience]
        try:
            plan = reanalyze_audience_plan(run_id, run, audience) if os.environ.get("GEMINI_API_KEY") else build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
        except Exception as exc:
            logger.warning("Audience media re-analysis failed for %s/%s; using deterministic fallback: %s", run_id, audience, exc)
            plan = build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
        run["plans"][audience] = plan
        arc_cache[audience] = promise_arc_from_plan(plan)
        save_runs()
        return arc_cache[audience]
    if "promise_arc" in run:
        promise_arc = run["promise_arc"]
        if "audience" in promise_arc:
            return promise_arc
    audience = run.get("trailer", {}).get("audience", "family")
    return promise_arc_from_plan(run["plans"].get(audience, run["plans"]["family"]))


@app.post("/runs/{run_id}/promise-arc")
def update_promise_arc(run_id: str, update: PromiseArcUpdate) -> dict:
    """Validate human intent edits, then regenerate the affected trailer plan."""
    run = get_run(run_id)
    if update.audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail="Unsupported audience.")
    scenes = {scene["id"]: scene for scene in run["story_map"].get("scenes", [])}
    segments = []
    for beat in update.narrative_arc:
        if not beat.included:
            continue
        scene = scenes.get(beat.scene_id)
        if not scene:
            raise HTTPException(status_code=422, detail=f"Unknown scene: {beat.scene_id}")
        source_in = parse_timecode(beat.source_in)
        source_out = parse_timecode(beat.source_out)
        if source_in < scene["start"] or source_out > scene["end"] or source_out <= source_in:
            raise HTTPException(status_code=422, detail=f"Invalid range for {beat.scene_id}; it must stay inside the source scene.")
        segments.append({
            "source_in": source_in, "source_out": source_out, "video": beat.scene_id,
            "label": beat.beat_name,
            "audio": "original_dialogue", "subtitle": "source_subtitles", "tone": scene.get("tone") or "discovery",
            "sensitive_content": scene.get("sensitiveContent", scene.get("sensitive_content", [])),
            "reason": beat.emotional_goal, "evidence": [f"scene:{beat.scene_id}", "human:promise_arc_edit"],
            "risk_flags": [], "scene_id": beat.scene_id, "start": source_in, "end": source_out,
            "spoiler_level": scene.get("spoilerLevel", scene.get("spoiler_level", "low")),
        })
    segments.sort(key=lambda item: item["start"])
    if not segments:
        raise HTTPException(status_code=422, detail="Include at least one narrative beat before regenerating the timeline.")
    constraint_map = run["constraint_map"]
    validation = Validator().validate(segments, {
        "scene_ids": constraint_map.get("metadata", {}).get("scene_ids", []),
        "cleared_scene_ids": constraint_map.get("metadata", {}).get("cleared_scene_ids", []),
        "expired_assets": constraint_map.get("metadata", {}).get("expired_assets", []),
        "protected_facts": constraint_map.get("metadata", {}).get("protected_facts", []),
        "audience": update.audience, "estimated_cost_usd": 0.02,
        "max_cost_usd": constraint_map.get("metadata", {}).get("max_cost_usd", 1.0),
    })
    plan = deepcopy(run["plans"].get(update.audience, run["plans"]["family"]))
    plan.update({"audience": update.audience, "audience_promise": update.audience_promise, "segments": segments,
                 "duration_seconds": sum(item["end"] - item["start"] for item in segments), "validation": validation})
    run["plans"][update.audience] = plan
    run["promise_arc"] = {**update.model_dump(), "validation_status": validation["status"]}
    run.setdefault("audience_arc_cache", {})[update.audience] = run["promise_arc"]
    run["trailer"] = trailer_from_plan(run_id, plan, run["story_map"]["title"])
    save_runs()
    return {"promise_arc": run["promise_arc"], "trailer": run["trailer"]}


@app.get("/runs/{run_id}/plans")
def get_plans(run_id: str) -> dict:
    run = get_run(run_id)
    return {"plans": run.get("plans", {}), "constraintMap": run.get("constraint_map", {}), "decisionLog": run.get("decision_log", [])}


@app.post("/runs/{run_id}/plan")
def plan_trailer(run_id: str) -> dict:
    return get_run(run_id)["trailer"]


@app.post("/runs/{run_id}/render")
def render_trailer(run_id: str) -> dict:
    output_path = render_segments(run_id, get_run(run_id))
    return {"url": f"/runs/{run_id}/render", "filename": output_path.name}


@app.get("/runs/{run_id}/render")
def download_rendered_trailer(run_id: str) -> FileResponse:
    output_path = RENDER_DIR / f"{run_id}.mp4"
    if not output_path.is_file():
        output_path = render_segments(run_id, get_run(run_id))
    return FileResponse(output_path, media_type="video/mp4", filename=f"{run_id}-trailer.mp4")