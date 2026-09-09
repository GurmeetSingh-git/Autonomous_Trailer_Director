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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate inputs and start a trailer director run."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.episode.exists():
        parser.error(f"episode package does not exist: {args.episode}")

    print(json.dumps({
        "status": "ready",
        "episode": str(args.episode.resolve()),
        "audience": args.audience,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
