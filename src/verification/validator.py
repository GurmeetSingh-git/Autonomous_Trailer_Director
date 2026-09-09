"""Run the independent verification pipeline."""

from typing import Any

try:
    from src.verification.accessibility_check import check as accessibility_check
    from src.verification.bias_check import check as bias_check
    from src.verification.budget_check import check as budget_check
    from src.verification.injection_check import check as injection_check
    from src.verification.rating_check import check as rating_check
    from src.verification.rights_check import check as rights_check
except ModuleNotFoundError:
    from verification.accessibility_check import check as accessibility_check
    from verification.bias_check import check as bias_check
    from verification.budget_check import check as budget_check
    from verification.injection_check import check as injection_check
    from verification.rating_check import check as rating_check
    from verification.rights_check import check as rights_check


class Validator:
    """Run all verification checks and return PASS or REJECT evidence."""

    def validate(self, candidate: Any, context: Any = None) -> dict[str, Any]:
        """Validate a candidate trailer against its context."""
        context = context or {}
        failures = []
        scene_ids = set(context.get("scene_ids", []))
        for item in candidate:
            if item.get("scene_id") not in scene_ids:
                failures.append({"check": "existence", "scene_id": item.get("scene_id"), "reason": "scene does not exist"})
            if item.get("spoiler_level") == "high":
                failures.append({"check": "spoiler", "scene_id": item.get("scene_id"), "reason": "high spoiler risk"})
            if item.get("end", 0) <= item.get("start", 0):
                failures.append({"check": "timing", "scene_id": item.get("scene_id"), "reason": "end must be after start"})
        checks = [{"name": "Existence and timing", "status": "fail" if failures else "pass"}]
        for name, passed in (
            ("Rights", rights_check(candidate, context)),
            ("Rating", rating_check(candidate, context)),
            ("Accessibility", accessibility_check(candidate, context)),
            ("Bias", bias_check(candidate, context)),
            ("Budget", budget_check(candidate, context)),
            ("Prompt injection", injection_check(candidate, context)),
        ):
            checks.append({"name": name, "status": "pass" if passed else "fail"})
            if not passed:
                failures.append({"check": name.lower().replace(" ", "_"), "reason": f"{name} constraint failed"})
        return {"status": "REJECT" if failures else "PASS_WITH_WARNINGS", "failures": failures, "checks": checks}


def run_checks(segments: list[dict], story_map: dict, constraint_map: dict, audience: str) -> dict[str, Any]:
    """Graph-compatible validation entrypoint."""
    del audience
    return Validator().validate(segments, {"scene_ids": constraint_map.get("metadata", {}).get("scene_ids", [s.get("id") for s in story_map.get("scenes", [])])})
