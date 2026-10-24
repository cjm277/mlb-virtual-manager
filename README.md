# MLB Virtual Manager

A multi-agent app that prepares an MLB manager for a game: it picks the lineup, fielding positions, starting pitcher and pitch mix, bullpen plan, and pinch-hit/pinch-run scenarios, and writes scouting reports on both teams, for any game on the 2026 schedule (stats up to the day before the game) or the published 2027 schedule (full-2026 stats and end-of-2026 rosters).

> **Status:** under construction. Setup steps below will be finalized before submission.

## Quick start

Requires **Python 3.11+**. No other software is needed.

1. **Clone the repo.**
   ```bash
   git clone https://github.com/cjm277/mlb-virtual-manager.git
   cd mlb-virtual-manager
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
| `backend/engine/` | Stats engine: stats as of the game (with the 2025 fade), splits, arsenals, matchups, rotation and lineup predictors, bullpen availability |
| `backend/tools.py` | The tools the agents call (plain Python over the data, no LLM inside) |
| `scripts/` | One-time data build, data spot-checks, and predictor evaluation (graders do not need to run these) |
| `data/` | The prebuilt 2026 stats snapshot the app reads |
| `tests/` | Automated tests |
| `evidence/` | Screenshots, logs, and test output that back up the report |
