"""Run the independent verification pipeline."""

from typing import Any

try:
    from src.verification.accessibility_check import check as accessibility_check
    from src.verification.bias_check import check as bias_check
    from src.verification.budget_check import check as budget_check
    from src.verification.injection_check import check as injection_check
    from src.verification.rating_check import check as rating_check
    from src.verification.rights_check import check as rights_check
    from src.verification.spoiler_check import check as spoiler_check
except ModuleNotFoundError:
    from verification.accessibility_check import check as accessibility_check
    from verification.bias_check import check as bias_check
    from verification.budget_check import check as budget_check
    from verification.injection_check import check as injection_check
    from verification.rating_check import check as rating_check
    from verification.rights_check import check as rights_check
    from verification.spoiler_check import check as spoiler_check


class Validator:
    """Run all verification checks and return PASS or REJECT evidence."""

    def validate(self, candidate: Any, context: Any = None) -> dict[str, Any]:
        """Validate a candidate trailer against its context."""
        context = context or {}
        failures = []
        check_results = []
        scene_ids = set(context.get("scene_ids", []))

        # Structural checks: existence and timing only. Spoiler risk moved to
        # its own independent check below — it no longer trusts item.get("spoiler_level"),
        # which the candidate-generation call set on itself.
        for item in candidate:
            if item.get("scene_id") not in scene_ids:
                failures.append({"check": "existence", "scene_id": item.get("scene_id"), "reason": "scene does not exist"})
            if item.get("end", 0) <= item.get("start", 0):
                failures.append({"check": "timing", "scene_id": item.get("scene_id"), "reason": "end must be after start"})

        structural_status = "fail" if failures else "pass"
        structural_detail = "; ".join(failure["reason"] for failure in failures) if failures else "All scene references and time ranges are valid."
        check_results.append({"name": "Existence and timing", "status": structural_status, "severity": structural_status, "detail": structural_detail})

        for name, result in (
            ("Spoiler", spoiler_check(candidate, context)),
            ("Rights", rights_check(candidate, context)),
            ("Rating", rating_check(candidate, context)),
            ("Accessibility", accessibility_check(candidate, context)),
            ("Bias", bias_check(candidate, context)),
            ("Budget", budget_check(candidate, context)),
            ("Prompt injection", injection_check(candidate, context)),
        ):
            check_results.append({"name": name, "severity": result["status"], "status": result["status"], "detail": result["detail"]})
            if result["status"] == "fail":
                failures.append({"check": name.lower().replace(" ", "_"), "reason": result["detail"]})

        severities = {check["severity"] for check in check_results}
        overall_status = "REJECT" if "fail" in severities else "PASS_WITH_WARNINGS" if "warning" in severities else "PASS"
        return {"status": overall_status, "failures": failures, "checks": check_results}


def run_checks(segments: list[dict], story_map: dict, constraint_map: dict, audience: str) -> dict[str, Any]:
    """Graph-compatible validation entrypoint."""
    metadata = constraint_map.get("metadata", {})
    return Validator().validate(
        segments,
        {
            "scene_ids": metadata.get("scene_ids", [s.get("id") for s in story_map.get("scenes", [])]),
            "cleared_scene_ids": metadata.get("cleared_scene_ids", []),
            "expired_assets": metadata.get("expired_assets", []),
            "protected_facts": metadata.get("protected_facts", []),
            "audience": audience,
            "estimated_cost_usd": 0.02,
            "max_cost_usd": metadata.get("max_cost_usd", 1.0),
        },
    )