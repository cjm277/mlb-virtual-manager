# MLB Virtual Manager

A multi-agent app that prepares an MLB manager for a game: it picks the lineup, fielding positions, starting pitcher and pitch mix, bullpen plan, and pinch-hit/pinch-run scenarios, and writes scouting reports on both teams, all from 2026 regular-season stats.

> **Status:** under construction. Setup steps below will be finalized before submission.

## Quick start

Requires **Python 3.11+**. No other software is needed.

1. **Clone the repo.**
   ```bash
   git clone <repo-url>
   cd <repo-folder>
   ```
2. **Add your API key.** The app looks for a `.env` file in this folder first, then in the folder above it. Copy `.env.example` and fill in `PORTKEY_API_KEY`.
3. **Create a virtual environment and install packages.**
   ```bash
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements.txt   # Windows
   .venv/bin/python -m pip install -r requirements.txt       # macOS / Linux
   ```
4. **Check the key is found** (the value is never printed).
   ```bash
   .venv/Scripts/python -m backend.config   # Windows
   .venv/bin/python -m backend.config       # macOS / Linux
   ```
5. **Run the app:** _coming soon._

## API keys

| Key | Used for |
|---|---|
| `PORTKEY_API_KEY` | All agent calls, through the course Portkey gateway with the `gpt-6-luna` model |

## Project layout

| Path | What it holds |
|---|---|
| `backend/` | Python backend: settings, stats engine, agents, API |
| `scripts/` | One-time data build script (graders do not need to run it) |
| `data/` | The prebuilt 2026 stats snapshot the app reads |
| `tests/` | Automated tests |
| `evidence/` | Screenshots, logs, and test output that back up the report |
