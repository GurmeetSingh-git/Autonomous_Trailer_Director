"""Detect visual shot boundaries and reconcile them with LLM-proposed timecodes."""

from scenedetect import detect, ContentDetector


def detect_scene_cuts(video_path: str, threshold: float = 30.0) -> list[dict]:
    """Return exact visual shot boundaries from local frame-diff analysis."""
    scene_list = detect(video_path, ContentDetector(threshold=threshold))
    cuts = []
    for index, scene in enumerate(scene_list):
        start_seconds = scene[0].get_seconds()
        end_seconds = scene[1].get_seconds()
        cuts.append({
            "id": f"s{index + 1:02d}",
            "start": start_seconds,
            "end": end_seconds,
            "timecode": scene[0].get_timecode(),
            "end_timecode": scene[1].get_timecode(),
        })
    return cuts


def snap_to_nearest_cut(timecode_seconds: float, cuts: list[dict], max_drift_seconds: float = 2.0) -> float:
    """Move an LLM-proposed timecode onto the nearest real shot boundary.

    Only snaps if a boundary is within max_drift_seconds; otherwise the
    original (unsnapped) timecode is returned unchanged.
    """
    if not cuts:
        return timecode_seconds
    boundary_points = sorted({cut["start"] for cut in cuts} | {cut["end"] for cut in cuts})
    nearest = min(boundary_points, key=lambda point: abs(point - timecode_seconds))
    if abs(nearest - timecode_seconds) <= max_drift_seconds:
        return nearest
    return timecode_seconds


def snap_scene_to_cuts(scene: dict, cuts: list[dict], max_drift_seconds: float = 2.0) -> dict:
    snapped = dict(scene)
    for start_key, end_key in (("start", "end"), ("trailer_start", "trailer_end"), ("trailerStart", "trailerEnd")):
        if start_key in snapped:
            snapped[start_key] = snap_to_nearest_cut(snapped[start_key], cuts, max_drift_seconds)
        if end_key in snapped:
            snapped[end_key] = snap_to_nearest_cut(snapped[end_key], cuts, max_drift_seconds)

    # Re-clamp trailer sub-range inside the (possibly moved) outer scene range
    outer_start = snapped.get("start")
    outer_end = snapped.get("end")
    for start_key, end_key in (("trailer_start", "trailer_end"), ("trailerStart", "trailerEnd")):
        if start_key in snapped and outer_start is not None and outer_end is not None:
            snapped[start_key] = max(outer_start, min(snapped[start_key], outer_end))
            snapped[end_key] = max(snapped[start_key], min(snapped[end_key], outer_end))
    return snapped