# Autonomous Trailer Director

This repository contains a replayable, constraint-aware trailer planning pipeline and an optional Gemini-backed upload API.

## Live API and frontend

Create a local environment file from the committed template before using the live upload path:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and replace `your_gemini_api_key_here` with your Gemini API key. Never commit `.env` or put a real API key in `.env.example`.

Start the backend in one terminal:

```powershell
uvicorn api:app --reload --port 8000
```

The FastAPI backend runs at <http://127.0.0.1:8000>. Keep this terminal running.

In a second terminal, install the frontend dependencies and start Next.js:

```powershell
cd frontend
npm install
npm run dev
```

Keep both terminals running and open the frontend at <http://localhost:3000>.

The live path loads `GEMINI_API_KEY` and `GEMINI_MODEL` from `.env`.
Episode analysis continues in the background after upload. The frontend shows
the current analysis stage and visual-shot progress, then opens the Story Map
when the run completes. Visual checks are batched into labeled contact sheets
to reduce model calls while keeping each shot's evidence separate. Run progress
is available at `GET /runs/{run_id}/status`; if analysis fails after a
checkpoint is saved, the upload page offers a retry without re-uploading.

See [ARCHITECTURE.md](ARCHITECTURE.md), [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), and [validation_report.md](validation_report.md) for design and tradeoffs.
