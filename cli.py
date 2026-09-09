"""Command-line entrypoint for Autonomous Trailer Director."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from orchestration.pipeline import run_director


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Plan a trailer from an episode package.")
    parser.add_argument("--episode", required=True, type=Path, help="Episode package path.")
    parser.add_argument("--audience", default="family", help="Target audience, such as family.")
    parser.add_argument("--output", default="submission", type=Path, help="Directory for generated JSON artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate inputs and start a trailer director run."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.episode.exists():
        parser.error(f"episode package does not exist: {args.episode}")

    result = run_director(args.episode, args.output)
    artifacts = {
        "story_map.json": result["story_map"],
        "constraint_map.json": result["constraint_map"],
        "decision_log.json": result["decision_log"],
    }
    artifacts.update({f"{audience}_trailer.json": plan for audience, plan in result["plans"].items()})
    for filename, payload in artifacts.items():
        (args.output / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "episode": str(args.episode.resolve()),
        "audience": args.audience,
        "output": str(args.output.resolve()),
        "artifacts": sorted(artifacts),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
