# src/ingestion/video_scene_analyzer.py
from src.models.scene import SceneAnalysis   # pydantic model matching your JSON exactly
from src.llm.client import LLMClient

SCENE_ANALYSIS_PROMPT = """
You are analyzing a single scene clip from a TV episode. Given the video,
its audio transcript, and its timecodes, produce a structured analysis.
Do not infer facts not visible/audible in this clip. Do not speculate
about later scenes. If uncertain about spoiler_risk or sensitive_content,
mark it and explain why in spoiler_reason.
"""

def analyze_scene(scene_id: str, video_clip_path: str, transcript_segment: list[dict],
                   start: str, end: str, llm: LLMClient) -> SceneAnalysis:
    raw = llm.generate_structured(
        system_prompt=SCENE_ANALYSIS_PROMPT,
        media=video_clip_path,
        context={"transcript": transcript_segment, "start": start, "end": end},
        response_schema=SceneAnalysis,
    )
    raw.scene_id = scene_id
    raw.start, raw.end = start, end
    return raw