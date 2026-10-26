# MLB Virtual Manager

A multi-agent app that prepares an MLB manager for a game: it picks the lineup, fielding positions, starting pitcher and pitch mix, bullpen plan, and pinch-hit/pinch-run scenarios, and writes scouting reports on both teams, for any game on the 2026 schedule (stats up to the day before the game) or the published 2027 schedule (full-2026 stats and end-of-2026 rosters).


## Quick start

Requires **Python 3.11+**. No other software is needed.

1. **Clone the repo.**
   ```bash
   git clone https://github.com/cjm277/mlb-virtual-manager.git
   cd mlb-virtual-manager
   ```
   On Windows, clone into a folder with a short path, such as `Downloads`. If git reports "Filename too long" (some saved logs have long names, and Windows limits a full path to 260 characters), run `git config --global core.longpaths true` and clone again.
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
5. **Start the app.**
   ```bash
   .venv/Scripts/python app.py      # Windows
   .venv/bin/python app.py          # macOS / Linux
   ```
   Your browser opens to **http://localhost:8000**. Pick your team, an opponent and a game, then press **Build game plan** (about 1 minute and under 2 cents). Review and edit the plan (with the dropdowns, or by chatting with the assistant coach: "I don't like Clement in this matchup"), then **Download packets (ZIP)**. Saved plans under "Recent game plans" open instantly without using the API.

   Command-line alternative:
   ```bash
   .venv/Scripts/python run_plan.py --team TOR --opp BOS --list
   .venv/Scripts/python run_plan.py --team TOR --opp BOS --date 2027-05-03
   ```
   Each run writes `runs/<run_id>/plan.json` and `runs/<run_id>/audit.jsonl` (every agent step, tool call, token count, timing and cost).

## API keys

| Key | Used for |
|---|---|
| `PORTKEY_API_KEY` | All agent calls, through the course Portkey gateway with the `gpt-6-luna` model |

## Project layout

| Path | What it holds |
|---|---|
| `backend/engine/` | Stats engine: stats as of the game (with the 2025 fade), splits, arsenals, matchups, rotation and lineup predictors, bullpen availability |
| `backend/tools.py` | The tools the agents call (plain Python over the data, no LLM inside) |
| `backend/agents/` | The seven-agent staff, the run order and fix loop (`team.py`), and context-bound tools (`toolkit.py`) |
| `backend/prompts/` | One prompt file per agent, plus the shared rules |
| `backend/models.py` | Typed outputs for every element of the plan |
| `backend/checker.py` | The consistency checker: plan rules, plus "every quoted stat must come from a tool" |
| `run_plan.py` | Command-line runner |
| `app.py`, `backend/main.py` | Web app: FastAPI routes, and it serves the prebuilt React app |
| `frontend/` | React + Vite + TypeScript source; `frontend/dist/` is the prebuilt app (Node is only needed to change it) |
| `backend/edits.py`, `backend/chat.py`, `backend/export.py` | Manager edits (dropdowns or chat) + re-check; ZIP export (HTML + PDF by audience) |
| `design.md` | Look-and-feel choices |
| `SAFETY.md` | Threats, the defenses built for each, and the tests and screenshots that prove them |
| `backend/budget.py` | Daily spending cap and free reuse of a recently built plan |
| `scripts/win_impact.py`, `scripts/win_model.py` | Win model: is the staff's plan analytically more likely to win than the real manager's? 150 sampled 2026 games scored through expected runs and Pythagenpat (report: `evidence/tests/win_impact.md`) |
| `backend/engine/winmodel.py`, `scripts/lineup_params.py`, `scripts/value_model_search.py` | The win model's lineup optimizer and how its inputs were chosen from 2026 data (reports: `evidence/tests/lineup_params.md`, `value_model_search.md`, `win_model_lineup.md`) |
| `backend/engine/defense.py`, `scripts/fetch_defense.py`, `scripts/defense_rating_search.py`, `scripts/defense_params.py` | Defense in the win model: multi-year Outs Above Average by position and catcher framing, how the rating and its weight were chosen (reports: `evidence/tests/defense_rating_search.md`, `defense_params.md`, `win_model_defense.md`) |
| `scripts/projection_search.py` | The Marcel-style projection the win model uses (each player's 2026 numbers pooled with his 2025, chosen on a July-September hold-out; report: `evidence/tests/projection_search.md`) |
| `scripts/value_at_scale.py`, `scripts/direct_check_*.py`, `scripts/defense_caution.py` | The lineup insight's value, scored on every 2026 game (report: `evidence/tests/value_at_scale.md`) |
| `backend/engine/starter_rule.py`, `scripts/starter_rule_replay.py` | The season-aware starter rule (the Pitching Coach's `model_starter` tool) and its full-season replay (report: `evidence/tests/starter_rule.md`) |
| `evidence/user_test/` | The real-user session: write-up and screenshots |
| `evidence/tests/phase10_fresh_clone.md` | Fresh-clone dry run: setup timed step by step |
| `report.html`, `scripts/build_report.py` | The project report (self-contained HTML), and the script that builds it from `evidence/` |
| `slides.html`, `scripts/build_slides.py` | The slide deck (reveal.js from a CDN, images embedded; arrow keys to move, F for full screen) |
| `scripts/tokenomics.py` | Cost per game / month / season / league, the 100 and 10,000 users question, and the cost-cutting A/B test (report: `evidence/tests/phase8_tokenomics.md`) |
| `frontend/public/teams/` | Ballpark photos (freely licensed, from Wikimedia Commons); photographer and license for each are in `credits.json` and shown in the app |
| `scripts/` | One-time data build, data spot-checks, and predictor evaluation (graders do not need to run these) |
| `data/` | The prebuilt 2026 stats snapshot the app reads |
| `tests/` | Automated tests |
| `evidence/` | Screenshots, logs, and test output that back up the report |
