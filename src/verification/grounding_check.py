"""Verify that proposed segments are grounded in real scene content.

Lexical/metadata layer only — see KNOWN_LIMITATIONS.md. This does not
inspect frames, audio, or transcript directly; it checks segment claims
and timecodes against the scene record produced upstream (which, when
video_scene_analyzer.py has run, should itself carry multimodal evidence).
When that richer evidence isn't present on the scene, this check is a
deliberately conservative fallback: ambiguous cases fail rather than pass.
"""

import re
from typing import Any

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for",
    "with", "without", "her", "his", "their", "its", "that", "this",
    "she", "he", "they", "it", "is", "are", "was", "were", "does", "do",
}


def _words(text: str) -> set[str]:
    # Unicode-aware: [^\W\d_]+ matches letter runs in any script, not just a-z.
    return {w for w in re.findall(r"[^\W\d_]+", text.lower(), flags=re.UNICODE) if w not in _STOPWORDS and len(w) > 2}


def _scene_lookup(context: dict[str, Any]) -> dict[str, dict]:
    scenes = context.get("scenes", [])
    if isinstance(scenes, dict):
        return scenes
    return {scene.get("id"): scene for scene in scenes}


def _field(scene: dict, *names, default=None):
    for name in names:
        if name in scene and scene[name] is not None:
            return scene[name]
    return default


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def check(candidate: list[dict], context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context or {}
    scenes = _scene_lookup(context)
    issues: list[str] = []
    warnings: list[str] = []

    for item in candidate:
        scene_id = item.get("scene_id") or item.get("video")
        scene = scenes.get(scene_id)
        if not scene:
            continue  # existence/timing already flags this as a hard failure

        start = item.get("start", item.get("source_in"))
        end = item.get("end", item.get("source_out"))
        scene_start = _field(scene, "start", default=0)
        scene_end = _field(scene, "end", default=float("inf"))
        grounded_start = _field(scene, "trailer_start", "trailerStart", default=scene_start)
        grounded_end = _field(scene, "trailer_end", "trailerEnd", default=scene_end)

        if start is None or end is None:
            issues.append(f"{scene_id}: segment has no timecodes to verify")
            continue
        if start < scene_start or end > scene_end:
            issues.append(f"{scene_id}: source_in/source_out fall outside the scene's own boundaries")
            continue

        overlap = _overlap(start, end, grounded_start, grounded_end)
        if overlap <= 0:
            issues.append(f"{scene_id}: clip [{start:.1f}-{end:.1f}s] has zero overlap with the grounded window [{grounded_start:.1f}-{grounded_end:.1f}s] — treat as ungrounded")
        else:
            pad = max(2.0, 0.15 * (grounded_end - grounded_start))
            if start < grounded_start - pad or end > grounded_end + pad:
                warnings.append(f"{scene_id}: clip extends beyond the grounded window ({grounded_start:.1f}-{grounded_end:.1f}s) — partial overlap only")

        claim = " ".join(str(item.get(field, "")) for field in ("reason", "label"))
        source_text = " ".join(str(_field(scene, field, default="")) for field in ("description", "emotion", "tone"))
        claim_words, source_words = _words(claim), _words(source_text)
        if claim_words and source_words:
            shared = claim_words & source_words
            if not shared:
                issues.append(f"{scene_id}: claim ('{claim.strip()[:60]}') shares no terms with the scene's own description — treat as ungrounded")
            elif len(shared) / len(claim_words) < 0.34:
                warnings.append(f"{scene_id}: claim overlaps weakly with scene description ({len(shared)}/{len(claim_words)} terms) — verify manually")

    if issues:
        return {"status": "fail", "detail": "; ".join(issues)}
    if warnings:
        return {"status": "warning", "detail": "; ".join(warnings)}
    return {"status": "pass", "detail": "All segments stay within their grounded scene windows and match scene content."}