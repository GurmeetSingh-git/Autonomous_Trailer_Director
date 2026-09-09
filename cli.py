"""Command-line entrypoint for Autonomous Trailer Director."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Plan a trailer from an episode package.")
    parser.add_argument("--episode", required=True, type=Path, help="Episode package path.")
    parser.add_argument("--audience", required=True, help="Target audience, such as family.")
    parser.add_argument("--output", type=Path, default=Path("submission"), help="Artifact output directory.")
    parser.add_argument("--live", action="store_true", help="Use the live API path instead of deterministic replay mode.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate inputs and start a trailer director run."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.episode.exists():
        parser.error(f"episode package does not exist: {args.episode}")

    if args.live:
        print(json.dumps({"status": "live_api_required", "episode": str(args.episode.resolve()), "audience": args.audience}))
        return 0

    from orchestration.pipeline import run_director

    result = run_director(args.episode, args.output)
    for name, payload in (
        ("story_map.json", result["story_map"]),
        ("constraint_map.json", result["constraint_map"]),
        ("family_trailer.json", result["plans"]["family"]),
        ("young_adult_trailer.json", result["plans"]["young_adult"]),
        ("dialect_region_trailer.json", result["plans"]["dialect_region"]),
        ("decision_log.json", result["decision_log"]),
    ):
        (args.output / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve()), "audiences": ["family", "young_adult", "dialect_region"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
