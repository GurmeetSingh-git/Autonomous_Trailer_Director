"""FastAPI entrypoint for the Autonomous Trailer Director frontend."""

from copy import deepcopy
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from src.llm.client import LLMClient
from src.models.story_map import StoryMap
from src.constraints.constraint_engine import ConstraintEngine
from src.logging.decision_log import DecisionLog
from src.planning.audience_strategy import AUDIENCE_GOALS
from src.verification.validator import Validator
from src.orchestration.review_graph import regenerate_review
from src.ingestion.scene_detector import detect_scene_cuts, snap_scene_to_cuts
from src.orchestration.pipeline import AUDIENCES, build_plan, default_transition_after
from src.ingestion.transcribe import transcribe_audio
from src.ingestion.shot_records import build_shot_records
from src.ingestion.vision_pass import run_vision_pass, group_shots_for_vision
from src.rendering.text_overlays import build_drawtext_filter
from src.rendering.text_overlays import clamp_card_duration

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
PENDING_DIR = Path("runtime/pending")
RUNS_FILE = Path("runtime/runs.json")
AUDIENCE_ARC_CACHE_VERSION = 5
VISUAL_EVIDENCE_GROUPING_VERSION = 1

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


interrupted_run_ids = [
    run_id for run_id, run in runs.items() if run.get("status") == "processing"
]
for interrupted_run_id in interrupted_run_ids:
    runs[interrupted_run_id].update({
        "status": "failed",
        "stage": "failed",
        "error": "Analysis was interrupted when the API restarted. Retry the saved analysis if a checkpoint is available, or upload again.",
    })
if interrupted_run_ids:
    save_runs()


def resolve_ffmpeg_path() -> str:
    """Return the FFmpeg executable or raise a clear error when it is missing."""
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if ffmpeg:
        return ffmpeg
    raise FileNotFoundError("FFmpeg is not installed or not on PATH.")


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
                "source_shots": scene.get("sourceShots", scene.get("source_shots", [])),
            }
            for scene in story_map.get("scenes", [])
        ],
    }


class StoryCharacter(BaseModel):
    name: str
    role: str


class TextCard(BaseModel):
    content: str = ""
    emphasis: str = "bold"          # subtle | bold | dramatic
    position: str = "center"        # center | lower_third
    case: str = "upper"             # upper | as_written
    duration: float = 2.0           # seconds; clamped server-side
    reason: str = ""


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
    source_shots: list[str] = Field(default_factory=list)
    text_card: TextCard | None = None 


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
    transition_after: str | None = None
    transition_reason: str = "" 
    text_card: TextCard | None = None


class PromiseArcUpdate(BaseModel):
    audience: str = "family"
    audience_profile: str = ""
    audience_promise: str
    narrative_arc: list[PromiseBeat]
    feedback: str = ""
    target_duration_seconds: int | None = None


class AudienceCandidate(BaseModel):
    scene_id: str
    beat_name: str
    source_in: str
    source_out: str
    emotional_goal: str
    transition_after: str = "hard_cut"
    transition_reason: str = "" 


class AudienceCandidates(BaseModel):
    candidates: list[AudienceCandidate] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    action: str
    feedback: str = ""


class PlotReprocessRequest(BaseModel):
    feedback: str = ""


class PlotBeatProposal(BaseModel):
    scene_id: str
    beat_name: str
    emotional_goal: str
    source_in: str
    source_out: str
    included: bool = True
    transition_after: str = "hard_cut" 
    transition_reason: str = ""    
    text_card: TextCard | None = None 


class PlotRevision(BaseModel):
    audience_promise: str
    beats: list[PlotBeatProposal] = Field(default_factory=list)


STORY_MAP_PROMPT = """
Analyze the provided shot-level evidence (shot_evidence) and produce a
spoiler-aware story map. Do not use raw video or audio directly — reason
only over the structured evidence given to you.

Each item in shot_evidence has a shot_id, start/end time in seconds, an
audio field (dialogue and non-verbal events), and — where visual_needed is
true — a visual field describing characters, appearance, actions, location,
and objects confirmed by inspecting actual video frames.

Use VISUAL evidence as the source of truth for actions, locations,
characters, non-dialogue moments, establishing shots, and emotional visual
beats, especially for shots with little or no dialogue. Use AUDIO evidence
(dialogue) as the source of truth for spoken lines, narration, and factual
claims made aloud. Do not invent events, characters, or resolutions absent
from the evidence. If audio and visual evidence for a shot seem to
disagree, describe both rather than resolving the disagreement yourself.

Ignore opening and closing credits, cast and crew lists, production logos,
rating certificates, and title cards when identifying trailer-worthy story
moments. Never treat credit text or a title sequence as a story beat.
Group story footage into 4 to 8 distinct chronological story beats; do not
merge the whole episode into one or two broad scenes. For each scene return:
- start timecode and end_timecode in HH:MM:SS, spanning its shots
- source_shots: the shot_id values from shot_evidence this scene is built
  from — every scene must be grounded in real shot_ids; never invent one
- content_start_timecode and content_end_timecode for the shortest
  self-contained trailer-worthy beat, normally 10-15 seconds, inside the
  scene boundaries and inside the referenced shots, grounded in visible
  action or spoken dialogue, not chosen by duration alone
- spoiler_level: low, medium, or high
- an emotion and concise tone such as wonder, tension, stakes, humour,
  discovery, or calm

Keep descriptions concise; don't invent names when unknown. spoiler_budget
is the max percentage of the episode revealable without spoiling the
ending — choose a sensible value between 10 and 30.

For any scene that would benefit from a standalone text card — an opening
hook, a title-like statement, or a moment that needs a beat of silence and
text rather than more footage — set text_card with:
- content: a short punchy line (3-8 words), grounded only in the evidence
  given; never invent plot facts, names, or dates not present in shot_evidence
- emphasis: "dramatic" for a major turn, "bold" for a standard beat,
  "subtle" for a quieter connective line
- position: "center" for a standalone card, "lower_third" to overlay text
  on the shot rather than replace it with black
- duration: seconds the card should hold, between 1.2 and 3.5 — longer for
  denser text, shorter for a single punchy line
- reason: one sentence grounded in the evidence explaining why this card
  earns its place

Not every scene needs a card — leave text_card unset (null) for most scenes.
Use judgment; two or three well-placed cards across the whole episode beat
one on every scene.
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
    background_tasks: BackgroundTasks,
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

    selected_model = model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not selected_model.startswith("gemini-"):
        video_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Invalid Gemini model selection.")

    runs[run_id] = {
        "audience": audience,
        "status": "processing",
        "stage": "queued",
        "error": None,
        "filename": safe_name,
        "video_path": str(video_path),
    }
    save_runs()
    background_tasks.add_task(
        process_episode, run_id, audience, safe_name, video_path, supporting_files, selected_model
    )
    return {"runId": run_id}


def update_run_progress(run_id: str, stage: str) -> None:
    runs[run_id].update({"status": "processing", "stage": stage, "progress": None})
    save_runs()


def update_visual_progress(run_id: str, processed: int, total: int) -> None:
    runs[run_id]["progress"] = {"processed": processed, "total": total}
    if processed == total or processed % 25 == 0:
        logger.info(
            "Run %s visual analysis: %d/%d shots processed.",
            run_id, processed, total,
        )
        save_runs()


def process_episode(
    run_id: str,
    audience: str,
    safe_name: str,
    video_path: Path,
    supporting_files: dict,
    selected_model: str,
) -> None:
    try:
        audio_path = UPLOAD_DIR / f"{run_id}_extracted_audio.wav"
        update_run_progress(run_id, "extracting_audio")
        ffmpeg = resolve_ffmpeg_path()
        audio_cmd = [
            ffmpeg, "-y", "-nostdin", "-hide_banner", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(audio_path),
        ]
        try:
            subprocess.run(audio_cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            detail = stderr.strip()[-2000:] or "FFmpeg returned no diagnostic output."
            raise RuntimeError(
                f"FFmpeg audio extraction failed (exit code {exc.returncode}): {detail}"
            ) from exc
        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            raise RuntimeError("Audio extraction failed; cannot analyze episode without audio.")
        supporting_files["extracted_audio"] = {"filename": audio_path.name, "path": str(audio_path)}

        update_run_progress(run_id, "detecting_scenes")
        try:
            detected_scenes = detect_scene_cuts(str(video_path))
            logger.info("PySceneDetect found %d visual boundaries.", len(detected_scenes))
        except Exception:
            logger.exception("PySceneDetect processing failed for run %s", run_id)
            detected_scenes = []
        supporting_files["pyscenedetect_cuts"] = detected_scenes

        llm = LLMClient(mode="live")
        update_run_progress(run_id, "transcribing_audio")
        try:
            audio_events = transcribe_audio(str(audio_path), llm, cache_key=run_id, model=selected_model)
            logger.info("Transcribed %d fine-grained audio segments.", len(audio_events))
        except Exception:
            logger.exception("Transcription failed for run %s", run_id)
            audio_events = []

        shot_records = build_shot_records(detected_scenes, audio_events)
        preview_groups = group_shots_for_vision(shot_records)
        flagged_shot_count = sum(shot.visual_needed for shot in shot_records)
        calls_with_grouping = sum(
            1 for group in preview_groups if len(group) > 1 or group[0].visual_needed
        )
        logger.info(
            "Run %s: %d shot records, %d flagged for visual inspection across %d calls.",
            run_id, len(shot_records), flagged_shot_count, calls_with_grouping,
        )

        update_run_progress(run_id, "analyzing_visuals")
        shot_records = run_vision_pass(
            shot_records,
            str(video_path),
            llm,
            model=selected_model,
            progress_callback=lambda processed, total: update_visual_progress(
                run_id, processed, total
            ),
        )
        shot_evidence = [record.model_dump() for record in shot_records]
        logger.info("Built visual evidence for %d shot records in run %s.", len(shot_evidence), run_id)

        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        pending_path = PENDING_DIR / f"{run_id}.json"
        pending_path.write_text(json.dumps({
            "audience": audience,
            "filename": safe_name,
            "video_path": str(video_path),
            "audio_path": str(audio_path),
            "selected_model": selected_model,
            "supporting_files": supporting_files,
            "detected_scenes": detected_scenes,
            "shot_records": shot_evidence,
        }), encoding="utf-8")

        update_run_progress(run_id, "building_story_map")
        generated = llm.generate_structured(
            system_prompt=STORY_MAP_PROMPT,
            media=None,
            context={
                "audience": audience,
                "filename": safe_name,
                "supporting_evidence": supporting_files,
                "shot_evidence": shot_evidence,
            },
            response_schema=GeneratedStoryMap,
            cache_key=run_id,
            model=selected_model,
        )
        if not generated.scenes:
            raise RuntimeError("The model returned no story beats for this episode.")

        _complete_run_from_story_map(
            run_id, generated, audience, safe_name, video_path, supporting_files,
            detected_scenes, shot_evidence, pending_path,
        )
    except Exception as exc:
        logger.exception("Episode analysis failed for run %s", run_id)
        runs[run_id].update({
            "status": "failed",
            "stage": "failed",
            "error": str(exc),
            "progress": None,
        })
        save_runs()


@app.get("/runs/{run_id}/status")
def get_run_status(run_id: str) -> dict[str, object]:
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    status = run.get("status", "complete" if "story_map" in run else "failed")
    return {
        "runId": run_id,
        "status": status,
        "stage": run.get("stage", status),
        "error": run.get("error"),
        "canRecover": (PENDING_DIR / f"{run_id}.json").is_file(),
        "progress": run.get("progress"),
    }


def resolve_render_range(segment: dict, shot_records_by_id: dict[str, dict]) -> tuple[float, float]:
    """Snap a segment's render range onto exact shot boundaries.

    Only source_shots that overlap the already-selected start/end window
    are used, so a scene's full shot list (which may span more than the
    chosen trailer sub-range) doesn't silently widen the clip.
    """
    fallback_start = parse_timecode(segment["start"]) if isinstance(segment["start"], str) else segment["start"]
    fallback_end = parse_timecode(segment["end"]) if isinstance(segment["end"], str) else segment["end"]
    shot_ids = segment.get("source_shots") or []
    overlapping = [
        shot_records_by_id[shot_id]
        for shot_id in shot_ids
        if shot_id in shot_records_by_id
        and shot_records_by_id[shot_id]["end"] > fallback_start
        and shot_records_by_id[shot_id]["start"] < fallback_end
    ]
    if not overlapping:
        return fallback_start, fallback_end
    return min(s["start"] for s in overlapping), max(s["end"] for s in overlapping)

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


def is_credit_or_title_shot(shot: dict) -> bool:
    """Identify non-story shots, discounting incidental text in story footage."""
    visual = shot.get("visual") or {}
    evidence = " ".join(
        [
            shot.get("audio", {}).get("dialogue", ""),
            *shot.get("audio", {}).get("events", []),
            *visual.get("actions", []),
            *visual.get("objects", []),
        ]
    )
    explicit_credit_evidence = bool(re.search(
        r"\b(?:opening credits|closing credits|end credits|opening title|film title|"
        r"cast list|crew list|producer list|producer names|names of producers|production credits|"
        r"produced by|executive producer|directed by|written by|production logo|"
        r"rating certificate|censor certificate|title card|copyright notice)\b",
        evidence,
        re.IGNORECASE,
    ))
    if explicit_credit_evidence:
        return True
    if visual.get("is_credit_or_title"):
        has_story_context = bool(visual.get("actions")) and bool(visual.get("location"))
        if not has_story_context:
            return True
    return False


def is_generic_beat_name(name: str, *titles: str) -> bool:
    normalized = re.sub(r"\s+", " ", name.strip()).casefold()
    if not normalized:
        return True
    title_names = [
        re.sub(r"\s+", " ", title.strip()).casefold()
        for title in titles
        if title
    ]
    if any(
        re.fullmatch(
            rf"{re.escape(title)}(?:\s+(?:part|chapter)\s+(?:\d+|one|two|three|four|five|six))?",
            normalized,
        )
        for title in title_names
    ):
        return True
    return bool(re.fullmatch(
        r"(?:story\s+)?(?:beat|moment|clip|part)(?:\s+(?:\d+|one|two|three|four|five|six))?",
        normalized,
    ))


def compact_scene_shot_evidence(
    scene: dict, shot_by_id: dict[str, dict], max_shots: int = 240
) -> list[dict]:
    """Keep a time-distributed, compact evidence sample for model selection."""
    scene_shots = [
        shot_by_id[shot_id]
        for shot_id in scene.get("source_shots", [])
        if shot_id in shot_by_id and not is_credit_or_title_shot(shot_by_id[shot_id])
    ]
    if len(scene_shots) > max_shots:
        stride = (len(scene_shots) + max_shots - 1) // max_shots
        sampled = {shot["shot_id"]: shot for shot in scene_shots[::stride]}
        for shot in scene_shots:
            if shot.get("audio", {}).get("dialogue", "").strip():
                sampled[shot["shot_id"]] = shot
        scene_shots = sorted(sampled.values(), key=lambda shot: shot["start"])
    return [
        {
            "shot_id": shot["shot_id"],
            "start": shot["start"],
            "end": shot["end"],
            "audio": {
                "dialogue": shot.get("audio", {}).get("dialogue", "")[:240],
                "events": shot.get("audio", {}).get("events", [])[:3],
            },
            "visual": {
                "characters": (shot.get("visual") or {}).get("characters", [])[:4],
                "actions": (shot.get("visual") or {}).get("actions", [])[:4],
                "location": (shot.get("visual") or {}).get("location", [])[:3],
                "objects": (shot.get("visual") or {}).get("objects", [])[:4],
                "is_credit_or_title": bool((shot.get("visual") or {}).get("is_credit_or_title")),
            },
        }
        for shot in scene_shots
    ]


def refresh_episode_wide_visual_evidence(run: dict, model: str) -> None:
    """Re-analyze legacy runs whose one vision summary was copied episode-wide."""
    if run.get("visual_evidence_grouping_version") == VISUAL_EVIDENCE_GROUPING_VERSION:
        return
    shots = run.get("shot_records", [])
    video_path = Path(run.get("video_path", ""))
    if len(shots) < 8 or not video_path.is_file():
        return
    visual_signatures = {
        json.dumps(shot.get("visual") or {}, sort_keys=True)
        for shot in shots
        if shot.get("visual")
    }
    if len(visual_signatures) != 1:
        run["visual_evidence_grouping_version"] = VISUAL_EVIDENCE_GROUPING_VERSION
        return

    from src.models.shot import ShotRecord

    logger.info(
        "Refreshing broad shared visual evidence for %d shots from %s",
        len(shots),
        video_path,
    )
    refreshed = run_vision_pass(
        [ShotRecord.model_validate(shot) for shot in shots],
        str(video_path),
        LLMClient(mode="live"),
        model=model,
    )
    run["shot_records"] = [shot.model_dump() for shot in refreshed]
    run["visual_evidence_grouping_version"] = VISUAL_EVIDENCE_GROUPING_VERSION
    save_runs()


def requested_duration_seconds(feedback: str) -> int | None:
    """Read an explicit trailer duration from natural-language director notes."""
    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*[- ]?\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b",
        feedback,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = 3600 if unit.startswith(("hour", "hr")) else 60 if unit.startswith("min") else 1
    return max(1, round(value * multiplier))


def target_cut_count(duration_seconds: int | None) -> int:
    """Use a concise six-cut default, scaling up for unusually long trailers."""
    if duration_seconds is None:
        return 6
    return min(30, max(6, round(duration_seconds / 15)))


def requested_cut_count(feedback: str) -> int | None:
    match = re.search(
        r"\b(?:at\s+least\s+|minimum\s+of\s+)?(\d+)(?:\s*[-–]\s*(\d+))?\s*"
        r"(?:cuts?|clips?|beats?)\b",
        feedback,
        re.IGNORECASE,
    )
    if not match:
        return None
    return max(1, int(match.group(2) or match.group(1)))


def enforce_target_duration(total_seconds: float, target_seconds: int | None) -> None:
    if target_seconds is None:
        return
    tolerance = max(2.0, target_seconds * 0.01)
    if abs(total_seconds - target_seconds) > tolerance:
        raise ValueError(
            f"The selected clips total {format_timecode(total_seconds)}; "
            f"the requested runtime is {format_timecode(target_seconds)}. "
            "Reprocess the plot to fill the requested runtime."
        )


def reanalyze_audience_plan(run_id: str, run: dict, audience: str) -> dict:
    """Ask the model for fresh, audience-grounded moments from shot evidence."""
    story_map = planning_story_map(run)
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    refresh_episode_wide_visual_evidence(run, model)
    shot_records = run.get("shot_records", [])
    shot_by_id = {shot["shot_id"]: shot for shot in shot_records}
    context = {
        "audience": audience,
        "audience_goal": AUDIENCE_GOALS[audience],
        "scenes": [
            {
                **{key: scene.get(key) for key in ("id", "start", "end", "description", "emotion", "tone", "characters", "spoiler_level")},
                "shot_evidence": compact_scene_shot_evidence(scene, shot_by_id),
            }
            for scene in story_map["scenes"]
        ],
    }
    prompt = """
Review the shot_evidence attached to each scene for the requested audience.
Select exactly six distinct, non-spoiler story moments that form a trailer
arc: opening hook, setup, rising tension, emotional stakes, escalation, and
an unresolved final button. These are six separate clips, not six labels for
the same scene or adjacent slices of one source passage.
Ground every choice only in the audio and visual evidence already given —
do not invent anything absent from it. Use precise HH:MM:SS.ss timecodes
derived from the shot boundaries. Omit credits, cast/crew or producer names,
production logos, rating certificates, opening titles, and any title-card
footage. Spread clip windows across the available story and leave at least
five seconds of unused source between selected windows. Vary emotional
energy and visual action rather than retelling one continuous passage.
Give every moment a concise, specific trailer beat_name and an emotional_goal.
Do not use the episode/scene title, producer or cast names, or generic
"Part One"/numbered titles as beat names.

For each moment, also choose transition_after — the cut style leading INTO the
next beat: "hard_cut" for a direct punchy cut; "micropause" for a brief beat
of black that lets a moment land; "fade_to_black" for a slower fade, used
sparingly, typically right before a major emotional turn or the final beat;
"crossfade" for a smooth blend between two visually or emotionally connected
moments, without going through black. Use hard_cut for most transitions;
reserve the others for moments that earn them.

For every moment, also fill transition_reason with one concise sentence grounded
in the shot_evidence of THIS moment and the next one — e.g. "Crossfade because
both shots share the same lantern-lit hallway" or "Hard cut because the next
beat jumps from calm to immediate danger." Never leave transition_reason empty
and never invent evidence not present in the shot_evidence.
"""
    result = LLMClient(mode="live").generate_structured(
        system_prompt=prompt,
        media=None,
        context=context,
        response_schema=AudienceCandidates,
        cache_key=f"{run_id}-{audience}",
        model=model,
    )
    scenes = {scene["id"]: scene for scene in story_map["scenes"]}
    segments = []
    for candidate in result.candidates[:6]:
        scene = scenes.get(candidate.scene_id)
        if not scene:
            continue
        start = parse_timecode(candidate.source_in)
        end = parse_timecode(candidate.source_out)
        if scene["spoiler_level"] == "high" or start < scene["start"] or end > scene["end"] or end <= start:
            continue
        if is_generic_beat_name(candidate.beat_name, scene.get("title", ""), story_map.get("title", "")):
            continue
        scene_shots = [
            shot_by_id[shot_id]
            for shot_id in scene.get("source_shots", [])
            if shot_id in shot_by_id
        ]
        overlapping_shots = [
            shot for shot in scene_shots
            if float(shot["end"]) > start and float(shot["start"]) < end
        ]
        if scene_shots and (
            not overlapping_shots
            or any(is_credit_or_title_shot(shot) for shot in overlapping_shots)
        ):
            continue
        segments.append({
            "source_in": start,
            "source_out": end,
            "video": scene["id"],
            "label": candidate.beat_name.strip(),
            "audio": "original_dialogue",
            "subtitle": "source_subtitles",
            "tone": scene.get("tone") or "discovery",
            "sensitive_content": scene.get("sensitive_content", []),
            "reason": candidate.emotional_goal,
            "evidence": [f"scene:{scene['id']}", "human:audience_reanalysis"],
            "risk_flags": [],
            "scene_id": scene["id"],
            "start": start,
            "end": end,
            "spoiler_level": scene["spoiler_level"],
            "transition_after": candidate.transition_after,
            "transition_reason": candidate.transition_reason,
            "source_shots": scene.get("source_shots", []),
        })
    if len(segments) != 6:
        raise ValueError(f"The model returned {len(segments)} distinct trailer moments; six are required.")
    source_order = sorted(segments, key=lambda item: item["start"])
    if any(current["start"] - previous["end"] < 5 for previous, current in zip(source_order, source_order[1:])):
        raise ValueError("The model selected adjacent source moments instead of distinct trailer cuts.")
    validation = Validator().validate(segments, {
        "scene_ids": run["constraint_map"].get("metadata", {}).get("scene_ids", []),
        "cleared_scene_ids": run["constraint_map"].get("metadata", {}).get("cleared_scene_ids", []),
        "expired_assets": run["constraint_map"].get("metadata", {}).get("expired_assets", []),
        "protected_facts": run["constraint_map"].get("metadata", {}).get("protected_facts", []),
        "scenes": story_map["scenes"],
        "audience": audience, "estimated_cost_usd": 0.02,
        "max_cost_usd": run["constraint_map"].get("metadata", {}).get("max_cost_usd", 1.0),
    })
    plan = build_plan(audience, story_map, run["constraint_map"], DecisionLog())
    plan.update({"segments": segments, "duration_seconds": sum(item["end"] - item["start"] for item in segments), "validation": validation})
    return plan


def promise_arc_from_plan(plan: dict, feedback: str = "") -> dict:
    """Expose the intent that precedes clip selection in an editable form."""
    return {
        "audience": plan["audience"],
        "audience_profile": plan["audience"],
        "audience_promise": plan["audience_promise"],
        "target_duration_seconds": plan.get("target_duration_seconds"),
        "narrative_arc": [
            {
                "scene_id": segment["scene_id"],
                "beat_name": segment.get("label") or f"Story beat {index + 1}",
                "source_in": format_editable_timecode(segment["start"]),
                "source_out": format_editable_timecode(segment["end"]),
                "emotional_goal": segment["reason"],
                "included": True,
                "transition_after": segment.get("transition_after", "hard_cut"),
                "transition_reason": segment.get("transition_reason", ""),
                "text_card": segment.get("text_card"),
            }
            for index, segment in enumerate(plan["segments"])
        ],
        "validation_status": plan["validation"]["status"],
        "feedback": feedback,
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
            "sourceShots": scene.source_shots,
            "selected": scene.spoiler_level != "high",
            "textCard": scene.text_card.model_dump() if scene.text_card else None, 
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
                "transition_after": segment.get("transition_after", "hard_cut"),
                "text_card": segment.get("text_card"),
                "transition_reason": segment.get("transition_reason", ""),
                "source_shots": segment.get("source_shots", []),
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


def _complete_run_from_story_map(
    run_id: str,
    generated: GeneratedStoryMap,
    audience: str,
    filename: str,
    video_path: Path,
    supporting_files: dict,
    detected_scenes: list[dict],
    shot_evidence: list[dict],
    pending_path: Path,
) -> None:
    """Build and persist a completed run after Story Map generation succeeds."""
    normalized_scenes = normalize_scenes(generated.scenes, video_path)
    normalized_scenes = [
        snap_scene_to_cuts(scene, detected_scenes, max_drift_seconds=2.0)
        for scene in normalized_scenes
    ]
    story_map = {
        "title": generated.title,
        "logline": generated.logline,
        "spoilerBudget": generated.spoiler_budget,
        "characters": [
            {"name": character.name, "role": character.role, "color": color}
            for color, character in zip(("coral", "sky", "gold"), generated.characters)
        ],
        "scenes": normalized_scenes,
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
                "sensitive_content": scene.get("sensitiveContent", []),
                "source_shots": scene.get("sourceShots", []),
                "text_card": scene.get("textCard"), 
            }
            for scene in story_map["scenes"]
        ],
    }
    constraint_map = ConstraintEngine().build(StoryMap.model_validate(internal_story_map)).model_dump()
    log = DecisionLog()
    selected_audience = audience if audience in AUDIENCES else "family"
    plan = build_plan(selected_audience, internal_story_map, constraint_map, log)
    trailer = trailer_from_plan(run_id, plan, story_map["title"])
    runs[run_id] = {
        "status": "complete",
        "stage": "complete",
        "error": None,
        "story_map": story_map,
        "trailer": trailer,
        "plans": {selected_audience: plan},
        "planning_story_map": internal_story_map,
        "promise_arc": promise_arc_from_plan(plan),
        "constraint_map": constraint_map,
        "decision_log": log.as_list(),
        "filename": filename,
        "video_path": str(video_path),
        "supporting_files": supporting_files,
        "shot_records": shot_evidence,
        "visual_evidence_grouping_version": VISUAL_EVIDENCE_GROUPING_VERSION,
        "review_status": "PENDING",
        "review_feedback": "",
        "review_round": 0,
    }
    save_runs()
    pending_path.unlink(missing_ok=True)


@app.get("/runs/{run_id}/media")
def get_media(run_id: str) -> FileResponse:
    """Ask the model to revise the plot from the director's feedback."""
    run = get_run(run_id)
    media_path = Path(run.get("video_path", ""))
    if not media_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded media is no longer available")
    return FileResponse(media_path)


def render_segments_with_opencv(segments: list[dict], media_path: Path, output_path: Path, shot_records_by_id: dict[str, dict] | None = None) -> Path:
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
            start_val, end_val = resolve_render_range(segment, shot_records_by_id or {})
            start_frame = max(0, int(start_val * fps))
            end_frame = max(start_frame, int(end_val * fps))
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


def _black_clip(path: Path, duration: float, reference_clip: Path) -> None:
    """Generate a silent black clip matching the reference clip's resolution/fps."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FileNotFoundError("ffprobe is not installed")
    probe = subprocess.run(
        [
            ffprobe, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-of", "csv=p=0", str(reference_clip),
        ],
        capture_output=True, text=True, check=True,
    )
    width, height, framerate = probe.stdout.strip().split(",")
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={framerate}:d={duration}",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", str(duration),
            "-c:v", "libx264", "-c:a", "aac", "-ar", "48000",
            str(path),
        ],
        check=True, capture_output=True, text=True,
    )

def _text_card(path: Path, card: dict, duration: float, reference_clip: Path) -> None:
    ffprobe = shutil.which("ffprobe")
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "csv=p=0", str(reference_clip)],
        capture_output=True, text=True, check=True,
    )
    width, height, framerate = probe.stdout.strip().split(",")
    text_filter = build_drawtext_filter(
        card.get("content", ""), card.get("emphasis", "bold"),
        card.get("position", "center"), card.get("case", "upper"), duration,
    )
    subprocess.run(
        [shutil.which("ffmpeg"), "-y",
         "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={framerate}:d={duration}",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
         "-t", str(duration),
         "-vf", f"{text_filter},format=yuv420p,setsar=1",
         "-c:v", "libx264", "-c:a", "aac", "-ar", "48000",
         str(path)],
        check=True, capture_output=True, text=True,
    )
    
def _has_audio_stream(path: Path) -> bool:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return False
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(probe.stdout.strip())


def _crossfade_clip(current_path: Path, next_path: Path, output_path: Path, fade_duration: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg is not installed")

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FileNotFoundError("ffprobe is not installed")

    current_duration = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(current_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    duration_value = float(current_duration or 0.0)
    offset = max(0.0, duration_value - fade_duration)

    has_audio_a = _has_audio_stream(current_path)
    has_audio_b = _has_audio_stream(next_path)
    filter_parts = [f"[0:v][1:v]xfade=transition=fade:duration={fade_duration}:offset={offset:.3f},format=yuv420p[vout]"]
    cmd = [ffmpeg, "-y", "-i", str(current_path), "-i", str(next_path)]
    if has_audio_a and has_audio_b:
        filter_parts.append(f"[0:a][1:a]acrossfade=d={fade_duration}[aout]")
        cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-c:a", "aac", "-ar", "48000", str(output_path)]
    else:
        cmd += ["-filter_complex", ";".join(filter_parts), "-map", "[vout]", "-an", "-c:v", "libx264", str(output_path)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def render_segments_with_ffmpeg(segments: list[dict], media_path: Path, output_path: Path, shot_records_by_id: dict[str, dict] | None = None) -> Path:
    """Cut and concatenate source ranges, inserting micropauses and fades between beats."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("FFmpeg is not installed")

    MICROPAUSE_DURATION = 0.3
    FADE_DURATION = 0.6
    BLACK_HOLD_DURATION = 0.4

    with tempfile.TemporaryDirectory(prefix="trailer-render-") as temporary_dir:
        temporary_path = Path(temporary_dir)
        segment_paths: list[Path] = []
        path_transitions: list[str] = []

        for index, segment in enumerate(segments):
            clip_path = temporary_path / f"clip-{index}.mp4"
            start_val, end_val = resolve_render_range(segment, shot_records_by_id or {})
            duration = end_val - start_val
            transition = segment.get("transition_after", "hard_cut")
            
            card = segment.get("text_card")
            if card:
                card_path = temporary_path / f"card-{index}.mp4"
                card_duration = clamp_card_duration(card.get("duration", 2.0))
                # card needs a reference clip for resolution/fps; probe media_path directly
                _text_card(card_path, card, card_duration, media_path)
                segment_paths.append(card_path)
                path_transitions.append("hard_cut")

            video_filters = []
            audio_filters = []
            if transition == "fade_to_black":
                fade_start = max(0.0, duration - FADE_DURATION)
                video_filters.append(f"fade=t=out:st={fade_start}:d={FADE_DURATION}")
                audio_filters.append(f"afade=t=out:st={fade_start}:d={FADE_DURATION}")

            cmd = [
                ffmpeg, "-y", "-ss", str(start_val), "-to", str(end_val),
                "-i", str(media_path), "-map", "0:v:0", "-map", "0:a?",
            ]
            if video_filters:
                cmd += ["-vf", ",".join(video_filters)]
            if audio_filters:
                cmd += ["-af", ",".join(audio_filters)]
            cmd += [
                "-c:v", "libx264", "-c:a", "aac", "-ar", "48000", "-avoid_negative_ts", "make_zero",
                str(clip_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            segment_paths.append(clip_path)
            path_transitions.append(transition)

        final_paths: list[Path] = []
        for index, clip_path in enumerate(segment_paths):
            if index == 0:
                final_paths.append(clip_path)
                continue

            previous_transition = path_transitions[index - 1]
            if previous_transition == "crossfade":
                merged_path = temporary_path / f"crossfade-{index - 1}.mp4"
                _crossfade_clip(final_paths[-1], clip_path, merged_path, FADE_DURATION)
                final_paths[-1] = merged_path
                continue

            final_paths.append(clip_path)
            if previous_transition in ("micropause", "fade_to_black"):
                black_path = temporary_path / f"black-{index - 1}.mp4"
                gap_duration = MICROPAUSE_DURATION if previous_transition == "micropause" else BLACK_HOLD_DURATION
                _black_clip(black_path, gap_duration, clip_path)
                final_paths.append(black_path)

        concat_list = temporary_path / "concat.txt"
        concat_list.write_text("\n".join(f"file '{path.as_posix()}'" for path in final_paths), encoding="utf-8")
        subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    return output_path


def render_segments(run_id: str, run: dict) -> Path:
    media_path = Path(run.get("video_path", ""))
    if not media_path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded media is no longer available")
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RENDER_DIR / f"{run_id}.mp4"
    segments = run.get("trailer", {}).get("segments", [])
    if not segments:
        raise HTTPException(status_code=422, detail="The trailer has no renderable segments.")
    shot_records_by_id = {record["shot_id"]: record for record in run.get("shot_records", [])}
    if shutil.which("ffmpeg"):
        try:
            return render_segments_with_ffmpeg(segments, media_path, output_path, shot_records_by_id)
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip().splitlines()[-1] if exc.stderr else "FFmpeg could not render the trailer."
            raise HTTPException(status_code=503, detail=detail) from exc
    return render_segments_with_opencv(segments, media_path, output_path, shot_records_by_id)


def get_run(run_id: str) -> dict:
    if run_id == "demo-run":
        return {"story_map": deepcopy(DEMO_STORY_MAP), "trailer": deepcopy(DEMO_TRAILER)}
    try:
        return runs[run_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/runs/{run_id}/story-map/retry")
def retry_story_map(run_id: str, model: str = Form("")) -> dict[str, str]:
    """Resume Story Map generation from the expensive-analysis checkpoint."""
    pending_path = PENDING_DIR / f"{run_id}.json"
    if not pending_path.is_file():
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found.")
        if run.get("status") == "processing":
            raise HTTPException(
                status_code=409,
                detail=f"Episode analysis is still in progress ({run.get('stage', 'processing')}).",
            )
        if run.get("status") == "failed":
            raise HTTPException(
                status_code=409,
                detail=run.get("error") or "Analysis failed before a recovery checkpoint was saved. Upload the episode again.",
            )
        raise HTTPException(status_code=404, detail="No recoverable analysis found for this run.")
    try:
        checkpoint = json.loads(pending_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="The saved analysis checkpoint is unreadable.") from exc

    video_path = Path(checkpoint["video_path"])
    if not video_path.is_file():
        raise HTTPException(status_code=404, detail="The original uploaded video is no longer available.")
    selected_model = model or checkpoint["selected_model"]
    if not selected_model.startswith("gemini-"):
        raise HTTPException(status_code=400, detail="Invalid Gemini model selection.")

    try:
        generated = LLMClient(mode="live").generate_structured(
            system_prompt=STORY_MAP_PROMPT,
            media=None,
            context={
                "audience": checkpoint["audience"],
                "filename": checkpoint["filename"],
                "supporting_evidence": checkpoint["supporting_files"],
                "shot_evidence": checkpoint["shot_records"],
            },
            response_schema=GeneratedStoryMap,
            cache_key=f"{run_id}-retry-{uuid4().hex[:8]}",
            model=selected_model,
        )
        if not generated.scenes:
            raise HTTPException(status_code=502, detail="The model returned no story beats. Try another model or clip.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Story Map retry failed for run %s", run_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    _complete_run_from_story_map(
        run_id,
        generated,
        checkpoint["audience"],
        checkpoint["filename"],
        video_path,
        checkpoint["supporting_files"],
        checkpoint["detected_scenes"],
        checkpoint["shot_records"],
        pending_path,
    )
    return {"runId": run_id}


@app.get("/runs/{run_id}/story-map")
def get_story_map(run_id: str) -> dict:
    run = get_run(run_id)
    if "story_map" not in run:
        if run.get("status") == "processing":
            raise HTTPException(
                status_code=409,
                detail=f"Episode analysis is still in progress ({run.get('stage', 'processing')}).",
            )
        if run.get("status") == "failed":
            raise HTTPException(
                status_code=409,
                detail=run.get("error") or "Episode analysis failed before a story map was generated.",
            )
        raise HTTPException(status_code=500, detail="Run completed without a story map.")
    return run["story_map"]


@app.get("/runs/{run_id}/trailer")
def get_trailer(run_id: str) -> dict:
    return get_run(run_id)["trailer"]


@app.post("/runs/{run_id}/plot/reprocess")
def reprocess_plot(run_id: str, request: PlotReprocessRequest, audience: str = "family") -> dict:
    """Use the director's prompt as revision instructions and regenerate the audience plan."""
    run = get_run(run_id)
    if run_id == "demo-run" or audience not in AUDIENCES:
        raise HTTPException(status_code=400, detail="A real run and supported audience are required.")
    run.setdefault("audience_arc_cache", {}).pop(audience, None)
    feedback = request.feedback.strip()
    feedback_lower = feedback.lower()
    remove_match = re.search(r"remove\s+(?:the\s+)?(?:(\d+)(?:st|nd|rd|th)?|first|second|third|last)\s+beat", feedback_lower)
    target_duration = requested_duration_seconds(feedback)
    requested_cuts = requested_cut_count(feedback)
    target_cuts = target_cut_count(target_duration) if target_duration else requested_cuts

    try:
        if os.environ.get("GEMINI_API_KEY"):
            model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
            refresh_episode_wide_visual_evidence(run, model)
            current_plan = run.get("plans", {}).get(audience) or build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
            scenes = planning_story_map(run).get("scenes", [])
            shot_by_id = {shot["shot_id"]: shot for shot in run.get("shot_records", [])}
            target_instructions = (
                f"Return exactly {target_cuts} separate edit clips with a combined "
                f"source duration of {target_duration} seconds (within 3 percent). "
                "Make the clips distinct moments spread across the episode, not "
                "adjacent slices. Balance their individual lengths to reach the "
                "total without padding any one shot."
                if target_duration and target_cuts
                else (
                    f"Return at least {target_cuts} distinct edit clips."
                    if target_cuts
                    else "Keep the number of clips consistent with the director's notes."
                )
            )
            prompt = f"""
Revise the proposed trailer plot using the director's feedback as explicit instructions.
Decide what to add, remove, reorder, rename, or rewrite.
Follow the feedback exactly, even if it changes the number of story beats.
Use only the supplied scene IDs and exclude high-spoiler scenes.
Preserve useful beats when the feedback does not explicitly ask to remove them.
Ground every beat in the shot_evidence attached to its scene; do not invent
content absent from that evidence. Select story footage only. Never include
opening/closing credits, cast/crew or producer names, production logos,
rating certificates, film title footage, title cards, or written names visible
on screen. Do not generate any text cards or overlays.

Make the edit feel like a trailer, not a continuous scene or a chronological
summary: start with a compelling hook, establish only the premise, escalate
energy and stakes, alternate emotional/visual intensity, and end on an
unresolved button. Select moments from different parts of the source timeline.
Leave at least five seconds of unused source between clips. Avoid near-duplicate
actions and repeated shots. {target_instructions}

For each clip return a concise, story-specific beat_name, emotional_goal,
source_in, and source_out in HH:MM:SS.ss, grounded in the shot timestamps.
Do not use the episode/scene title or generic numbered/Part One labels as beat names.
Choose transition_after and transition_reason for the transition into the next
clip, using hard cuts for most clips and other transitions sparingly.

"""
            revision = LLMClient(mode="live").generate_structured(
                system_prompt=prompt,
                media=None,
                context={
                    "audience": audience,
                    "director_feedback": feedback,
                    "target_duration_seconds": target_duration,
                    "target_clip_count": target_cuts,
                    "current_plot": [{"scene_id": segment["scene_id"], "beat_name": segment.get("label", ""), "emotional_goal": segment.get("reason", "")} for segment in current_plan.get("segments", [])],
                    "available_scenes": [
                        {
                            "id": scene["id"],
                            "title": scene.get("title", ""),
                            "description": scene.get("description", ""),
                            "spoiler_level": scene.get("spoiler_level", "low"),
                            "start": scene.get("start", 0),
                            "end": scene.get("end", 0),
                            "shot_evidence": compact_scene_shot_evidence(scene, shot_by_id),
                        }
                        for scene in scenes
                    ],
                },
                response_schema=PlotRevision,
                cache_key=f"{run_id}-plot-revision-{len(feedback)}",
                model=model,
            )
            scene_by_id = {scene["id"]: scene for scene in scenes}
            segments = []
            for proposal in revision.beats:
                scene = scene_by_id.get(proposal.scene_id)
                if not scene or not proposal.included or scene.get("spoiler_level") == "high":
                    continue
                if is_generic_beat_name(
                    proposal.beat_name,
                    scene.get("title", ""),
                    run.get("story_map", {}).get("title", ""),
                ):
                    raise ValueError(f"Beat '{proposal.beat_name}' needs a specific story moment title.")
                start = parse_timecode(proposal.source_in)
                end = parse_timecode(proposal.source_out)
                scene_start = float(scene.get("start", 0))
                scene_end = float(scene.get("end", start))
                if start < scene_start or end > scene_end or end <= start:
                    raise ValueError(f"Beat '{proposal.beat_name}' has an invalid source range.")
                scene_shots = [
                    shot_by_id[shot_id]
                    for shot_id in scene.get("source_shots", [])
                    if shot_id in shot_by_id
                ]
                if scene_shots:
                    overlapping_shots = [
                        shot for shot in scene_shots
                        if float(shot["end"]) > start and float(shot["start"]) < end
                    ]
                    if not overlapping_shots or any(is_credit_or_title_shot(shot) for shot in overlapping_shots):
                        raise ValueError(f"Beat '{proposal.beat_name}' does not select eligible story footage.")
                segments.append({
                    "source_in": start,
                    "source_out": end,
                    "video": scene["id"],
                    "label": proposal.beat_name,
                    "audio": "original_dialogue",
                    "subtitle": "source_subtitles",
                    "tone": scene.get("tone") or scene.get("emotion") or "discovery",
                    "sensitive_content": scene.get("sensitive_content", []),
                    "reason": proposal.emotional_goal,
                    "evidence": [f"scene:{scene['id']}", "human:plot_feedback", "llm:plot_revision"],
                    "risk_flags": [],
                    "scene_id": scene["id"],
                    "start": start,
                    "end": end,
                    "spoiler_level": scene.get("spoiler_level", "low"),
                    "transition_after": getattr(proposal, "transition_after", "hard_cut"),
                    "transition_reason": getattr(proposal, "transition_reason", ""),
                    "source_shots": scene.get("source_shots", []),
                    "text_card": None,
                })
            if segments:
                chronological_segments = sorted(segments, key=lambda segment: segment["start"])
                if any(
                    current["start"] - previous["end"] < 5
                    for previous, current in zip(chronological_segments, chronological_segments[1:])
                ):
                    raise ValueError("Plot beats must be distinct source moments, not adjacent slices.")
                if len(chronological_segments) != sum(
                    1 for proposal in revision.beats
                    if proposal.included
                    and proposal.scene_id in scene_by_id
                    and scene_by_id[proposal.scene_id].get("spoiler_level") != "high"
                ):
                    raise ValueError("Every included plot beat must have a valid distinct source range.")
                if target_duration and len(chronological_segments) != target_cuts:
                    raise ValueError(
                        f"The requested {format_timecode(target_duration)} trailer needs "
                        f"{target_cuts} distinct clips; the model returned {len(chronological_segments)}."
                    )
                if requested_cuts and not target_duration and len(chronological_segments) < requested_cuts:
                    raise ValueError(
                        f"The director requested at least {requested_cuts} clips; "
                        f"the model returned {len(chronological_segments)}."
                    )
                plan = deepcopy(current_plan)
                plan.update({
                    "audience_promise": revision.audience_promise,
                    "segments": segments,
                    "duration_seconds": sum(item["end"] - item["start"] for item in segments),
                    "target_duration_seconds": target_duration,
                })
            else:
                plan = build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
        else:
            if target_duration or requested_cuts:
                raise HTTPException(
                    status_code=503,
                    detail="A live Gemini API key is required to select the requested number of distinct trailer clips.",
                )
            plan = build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Plot reprocessing failed for %s/%s: %s", run_id, audience, exc)
        raise HTTPException(status_code=502, detail=f"The plot could not be reprocessed: {exc}") from exc

    if remove_match and plan.get("segments"):
        requested = remove_match.group(1)
        if "last" in remove_match.group(0):
            remove_index = len(plan["segments"]) - 1
        elif "first" in remove_match.group(0):
            remove_index = 0
        elif "second" in remove_match.group(0):
            remove_index = 1
        elif "third" in remove_match.group(0):
            remove_index = 2
        else:
            remove_index = int(requested) - 1
        if 0 <= remove_index < len(plan["segments"]):
            plan["segments"].pop(remove_index)
            plan["duration_seconds"] = sum(segment["end"] - segment["start"] for segment in plan["segments"])
            plan["validation"] = Validator().validate(plan["segments"], {
                "scene_ids": run["constraint_map"].get("metadata", {}).get("scene_ids", []),
                "cleared_scene_ids": run["constraint_map"].get("metadata", {}).get("cleared_scene_ids", []),
                "expired_assets": run["constraint_map"].get("metadata", {}).get("expired_assets", []),
                "protected_facts": run["constraint_map"].get("metadata", {}).get("protected_facts", []),
                "scenes": planning_story_map(run).get("scenes", []),
                "audience": audience, "estimated_cost_usd": 0.02,
                "max_cost_usd": run["constraint_map"].get("metadata", {}).get("max_cost_usd", 1.0),
            })
    try:
        enforce_target_duration(plan.get("duration_seconds", 0), target_duration)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    plan["target_duration_seconds"] = target_duration
    if not plan.get("validation"):
        metadata = run["constraint_map"].get("metadata", {})
        plan["validation"] = Validator().validate(plan["segments"], {
            "scene_ids": metadata.get("scene_ids", []),
            "cleared_scene_ids": metadata.get("cleared_scene_ids", []),
            "expired_assets": metadata.get("expired_assets", []),
            "protected_facts": metadata.get("protected_facts", []),
            "scenes": planning_story_map(run).get("scenes", []),
            "audience": audience,
            "estimated_cost_usd": 0.02,
            "max_cost_usd": metadata.get("max_cost_usd", 1.0),
        })

    plot = promise_arc_from_plan(plan, feedback)
    run["plans"][audience] = plan
    run.setdefault("audience_arc_cache", {})[audience] = plot
    save_runs()
    return plot


@app.post("/runs/{run_id}/review")
def review_trailer(run_id: str, review: ReviewRequest) -> dict:
    """Record approval or run a LangGraph-backed feedback regeneration."""
    run = get_run(run_id)
    if run_id == "demo-run":
        raise HTTPException(status_code=400, detail="The demo trailer cannot be reviewed.")
    if review.action not in {"pass", "fail", "regenerate"}:
        raise HTTPException(status_code=400, detail="Review action must be pass, fail, or regenerate.")
    feedback = review.feedback.strip()
    if review.action == "fail" and not feedback:
        raise HTTPException(status_code=422, detail="Feedback is required when rejecting a trailer.")
    if review.action == "pass":
        run["review_status"] = "PASSED"
        run["review_feedback"] = feedback
    elif review.action == "fail":
        run["review_status"] = "NEEDS_REVISION"
        run["review_feedback"] = feedback
    else:
        plan = run["plans"].get(run["trailer"]["audience"])
        if plan is None:
            plan = build_plan(run["trailer"]["audience"], planning_story_map(run), run["constraint_map"], DecisionLog())
        result = regenerate_review({
            "audience": plan["audience"],
            "story_map": planning_story_map(run),
            "constraint_map": run["constraint_map"],
            "audience_promise": plan.get("audience_promise", ""),
            "feedback": feedback or run.get("review_feedback", ""),
            "plan": plan,
            "validation": plan["validation"],
            "review_status": "NEEDS_REVISION",
        })
        run["plans"][plan["audience"]] = result["plan"]
        run["trailer"] = trailer_from_plan(run_id, result["plan"], run["story_map"]["title"])
        run["review_status"] = "PENDING"
        run["review_feedback"] = feedback or run.get("review_feedback", "")
        run["review_round"] = run.get("review_round", 0) + 1
    run["trailer"]["review_status"] = run["review_status"]
    run["trailer"]["review_feedback"] = run.get("review_feedback", "")
    run["trailer"]["review_round"] = run.get("review_round", 0)
    save_runs()
    return {"trailer": run["trailer"], "review_status": run["review_status"], "review_round": run["review_round"]}


@app.get("/runs/{run_id}/promise-arc")
def get_promise_arc(run_id: str, audience: str | None = None, reanalyze: bool = False) -> dict:
    run = get_run(run_id)
    if audience:
        if audience not in AUDIENCES:
            raise HTTPException(status_code=400, detail="Unsupported audience.")
        if run.get("audience_arc_cache_version") != AUDIENCE_ARC_CACHE_VERSION:
            run["audience_arc_cache"] = {}
            run["audience_arc_cache_version"] = AUDIENCE_ARC_CACHE_VERSION
        arc_cache = run.setdefault("audience_arc_cache", {})

        if not reanalyze and audience in arc_cache:
            return arc_cache[audience]

        try:
            if reanalyze:
                plan = reanalyze_audience_plan(run_id, run, audience)
            else:
                plan = build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
        except Exception as exc:
            logger.warning("Audience %s failed for %s/%s; falling back to stored data: %s",
                            "reanalysis" if reanalyze else "planning", run_id, audience, exc)
            if reanalyze:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not find six distinct trailer moments: {exc}",
                ) from exc
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
    plan = run["plans"].get(audience)
    if plan is None:
        plan = build_plan(audience, planning_story_map(run), run["constraint_map"], DecisionLog())
        run.setdefault("plans", {})[audience] = plan
        save_runs()
    return promise_arc_from_plan(plan)


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
        if is_generic_beat_name(
            beat.beat_name,
            run.get("story_map", {}).get("title", ""),
        ):
            raise HTTPException(
                status_code=422,
                detail="Give each trailer beat a specific story-moment name instead of the episode title or a generic label.",
            )
        source_in = parse_timecode(beat.source_in)
        source_out = parse_timecode(beat.source_out)
        scene_start = float(scene["start"])
        scene_end = float(scene["end"])
        rounding_tolerance = 0.05
        if source_in < scene_start - rounding_tolerance or source_out > scene_end + rounding_tolerance or source_out <= source_in:
            raise HTTPException(status_code=422, detail=f"Invalid range for {beat.scene_id}; it must stay inside the source scene.")
        source_in = max(scene_start, source_in)
        source_out = min(scene_end, source_out)
        scene_shots = [
            shot for shot in run.get("shot_records", [])
            if shot["shot_id"] in set(scene.get("sourceShots", scene.get("source_shots", [])))
            and float(shot["end"]) > source_in
            and float(shot["start"]) < source_out
        ]
        if scene_shots and any(is_credit_or_title_shot(shot) for shot in scene_shots):
            raise HTTPException(
                status_code=422,
                detail="A selected beat contains opening/closing credits, a title, or other non-story footage.",
            )
        segments.append({
            "source_in": source_in,
            "source_out": source_out,
            "video": beat.scene_id,
            "label": beat.beat_name,
            "audio": "original_dialogue",
            "subtitle": "source_subtitles",
            "tone": scene.get("tone") or "discovery",
            "sensitive_content": scene.get("sensitiveContent", scene.get("sensitive_content", [])),
            "reason": f"{beat.emotional_goal}{f' Reviewer note: {update.feedback.strip()}' if update.feedback.strip() else ''}",
            "evidence": [f"scene:{beat.scene_id}", "human:promise_arc_edit", *(["human:plot_feedback"] if update.feedback.strip() else [])],
            "risk_flags": [],
            "scene_id": beat.scene_id,
            "start": source_in,
            "end": source_out,
            "spoiler_level": scene.get("spoilerLevel", scene.get("spoiler_level", "low")),
            "transition_after": beat.transition_after or "hard_cut",
            "source_shots": scene.get("sourceShots", scene.get("source_shots", [])),
            "transition_reason": beat.transition_reason or "",
            "text_card": None,
        })
    source_order = sorted(segments, key=lambda item: item["start"])
    if not segments:
        raise HTTPException(status_code=422, detail="Include at least one narrative beat before regenerating the timeline.")
    if any(
        current["start"] - previous["end"] < 5
        for previous, current in zip(source_order, source_order[1:])
    ):
        raise HTTPException(status_code=422, detail="Trailer beats must use distinct source moments, not adjacent slices.")
    total_duration = sum(item["end"] - item["start"] for item in segments)
    try:
        enforce_target_duration(total_duration, update.target_duration_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    for index, segment in enumerate(segments):
        if segment["transition_after"] not in {"hard_cut", "micropause", "fade_to_black", "crossfade"}:
            segment["transition_after"] = default_transition_after(index, len(segments))
    constraint_map = run["constraint_map"]
    validation = Validator().validate(segments, {
        "scene_ids": constraint_map.get("metadata", {}).get("scene_ids", []),
        "cleared_scene_ids": constraint_map.get("metadata", {}).get("cleared_scene_ids", []),
        "expired_assets": constraint_map.get("metadata", {}).get("expired_assets", []),
        "protected_facts": constraint_map.get("metadata", {}).get("protected_facts", []),
        "scenes": scenes,
        "audience": update.audience, "estimated_cost_usd": 0.02,
        "max_cost_usd": constraint_map.get("metadata", {}).get("max_cost_usd", 1.0),
    })
    plan = deepcopy(run["plans"].get(update.audience))
    if plan is None:
        plan = build_plan(update.audience, planning_story_map(run), constraint_map, DecisionLog())
    plan.update({"audience": update.audience, "audience_promise": update.audience_promise, "segments": segments,
                 "duration_seconds": total_duration, "target_duration_seconds": update.target_duration_seconds,
                 "validation": validation})
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)