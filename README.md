# Autonomous Trailer Director

This repository contains a replayable, constraint-aware trailer planning pipeline and an optional Gemini-backed upload API.

## How to get the code into your Machine
Step-1 : Create a folder where you want to set the code
Step-2 : Open the Autonomous Trailer Director project & copy the clone path.
Step-3 : Open cmd terminal in that new folder and run command- `git clone [paste the copied path]`

## Enviornment Setup

Step-1: Open terminal & run command `Copy-Item .env.example .env`
Step-2: Edit `.env` and replace `your_gemini_api_key_here` with your Gemini API key. Never commit `.env` or put a real API key in `.env.example`.
Step-3: create virtual enviornment `python -m venv .venv`


## Backend Run
Activate the `.venv` by cmd `.venv/scripts/activate`
Step-1: run command `pip install -r requirements.txt`
Step-2: run command `uvicorn api:app --reload --port 8000`

The FastAPI backend runs at <http://127.0.0.1:8000>. Keep this terminal running.

## Frontend Setup
Step-1: Open new terminal
Step-2: Install node.js from web
Step-3: verify node.js is installed properly by `npm -v`
Step-4: run `npm install` to install project dependencies
Step-5: run `npm run dev`

Keep both terminals running and open the frontend at <http://localhost:3000>.

The live path loads `GEMINI_API_KEY` and `GEMINI_MODEL` from `.env`.
Episode analysis continues in the background after upload. The frontend shows
the current analysis stage and visual-shot progress, then opens the Story Map
when the run completes. Visual checks are batched into labeled contact sheets
to reduce model calls while keeping each shot's evidence separate. Run progress
is available at `GET /runs/{run_id}/status`; if analysis fails after a
checkpoint is saved, the upload page offers a retry without re-uploading.

See [ARCHITECTURE.md](ARCHITECTURE.md), [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), and [validation_report.md](validation_report.md) for design and tradeoffs.
