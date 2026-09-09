"""Apply policies and contracts to a story map."""

import json
from pathlib import Path
from typing import Any

from src.models.constraint_map import ConstraintMap
from src.models.story_map import StoryMap


class ConstraintEngine:
    """Build constraints that govern trailer planning."""

    def build(
        self,
        story_map: StoryMap,
        policies: list[dict[str, Any]] | None = None,
        contracts_path: Path | None = None,
    ) -> ConstraintMap:
        """Create a constraint map from policies and contracts."""
        default_policies = [
            {"id": "no_major_spoilers", "rule": "exclude scenes matching protected_facts"},
            {"id": "source_accuracy", "rule": "scene ids and timecodes must exist"},
            {"id": "audience_safety", "rule": "exclude sensitive content for family"},
        ]
        contracts = self._load_contracts(contracts_path)
        all_scene_ids = [scene.get("id") for scene in story_map.scenes]

        return ConstraintMap(
            policies=policies or default_policies,
            metadata={
                "scene_ids": all_scene_ids,
                "cleared_scene_ids": contracts.get("cleared_scene_ids", []),
                "expired_assets": contracts.get("expired_assets", []),
                "protected_facts": [fact.model_dump() for fact in story_map.protected_facts],
                "max_cost_usd": contracts.get("max_cost_usd", 1.0),
            },
        )

    def _load_contracts(self, contracts_path: Path | None) -> dict[str, Any]:
        if contracts_path and contracts_path.exists():
            return json.loads(contracts_path.read_text())
        # No contracts supplied: return an empty (not permissive) set so
        # rights_check correctly warns rather than silently passing everything.
        return {"cleared_scene_ids": [], "expired_assets": [], "max_cost_usd": 1.0}