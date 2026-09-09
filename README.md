# Autonomous Trailer Director

This repository contains a replayable, constraint-aware trailer planning pipeline and an optional Gemini-backed upload API.

## Replay run

The evaluator-safe path requires no API key:

```powershell
.\.venv\Scripts\Activate.ps1
python cli.py --episode sample_run\episode --audience family --output submission
```

This writes `story_map.json`, `constraint_map.json`, three audience trailer plans, and `decision_log.json`.

## Live API and frontend

```powershell
uvicorn api:app --reload --port 8000
cd frontend
npm run dev
```

The live path loads `GEMINI_API_KEY` and `GEMINI_MODEL` from `.env`. Replay mode is the recommended evaluation mode because it is deterministic.

See [ARCHITECTURE.md](ARCHITECTURE.md), [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), and [validation_report.md](validation_report.md) for design and tradeoffs.
