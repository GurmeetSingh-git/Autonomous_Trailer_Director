# Autonomous Trailer Director

## Pipeline

1. `cli.py` accepts an episode path and runs the deterministic replay pipeline.
2. `pipeline.py` builds a source-backed story map and constraint map.
3. The planner creates separate promises and edit decision lists for `family`, `young_adult`, and `dialect_region`.
4. The validator checks scene existence, spoiler risk, and source timing before a plan is accepted.
5. Artifacts are written as JSON for editorial review and evaluator inspection.
6. The FastAPI path can replace replay generation with Gemini multimodal analysis when `GEMINI_API_KEY` is configured.

## Trust boundaries

- Model output is a proposal, never a validation decision.
- Scene IDs and timecodes are checked against the story map.
- High-spoiler scenes are excluded from the three replay plans.
- Rights, cultural approval, and final editorial approval remain human decisions until authoritative source contracts are supplied.

## Runtime modes

- Replay mode: deterministic, offline, no API key required.
- Live mode: uploads video to Gemini and requests a structured story map.
- The CLI produces the evaluator-facing artifacts under `submission/`.
