"""MLB Virtual Manager web API (FastAPI). It also serves the prebuilt React app from frontend/dist.

Routes
  GET  /api/health                     is the API key found, which model
  GET  /api/teams                      all 30 teams with colors
  GET  /api/games?team_id=&opponent_id= every 2026 (played) and 2027 (scheduled) game between two teams
  POST /api/runs                       start building a game plan -> {run_id}
  GET  /api/runs                       recent runs
  GET  /api/runs/{id}/events?since=N   live progress (agent steps, tool calls, tokens, cost)
  GET  /api/runs/{id}/plan             the finished plan
  GET  /api/runs/{id}/options          choices for the edit screen (available players, starters, roles)
  POST /api/runs/{id}/edits            apply the manager's edits and re-check the plan (no model calls)
  GET  /api/runs/{id}/export           ZIP of HTML + PDF files in hitters/, pitchers/, coaches/
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import config, tools
from backend.edits import ROLES, PlanEdits, apply_edits
from backend.engine.games import game, games_between, teams
from backend.export import export_zip
from backend.team_colors import MLB, colors

DIST = config.REPO_ROOT / "frontend" / "dist"
MAX_ACTIVE_RUNS = 2          # cost guard: at most two plans building at once
LIGHT_FIELDS = ("result", "output", "task", "game", "limits", "pricing", "by_agent", "text")

app = FastAPI(title="MLB Virtual Manager")
RUNS: dict[str, dict] = {}   # run_id -> {"events": [...], "done": bool, "error": str | None}


def _run_dir(run_id: str) -> Path:
    if not re.fullmatch(r"[\w\-]+", run_id):
        raise HTTPException(400, "Bad run id.")
    d = config.RUNS_DIR / run_id
    if not d.is_dir():
        raise HTTPException(404, "No such run.")
    return d


def _plan(run_id: str) -> dict:
    f = _run_dir(run_id) / "plan.json"
    if not f.exists():
        raise HTTPException(409, "The plan is still being built.")
    return json.loads(f.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    config.load_env()
    import os
    return {"ok": True, "model": config.MODEL_NAME, "api_key_found": bool(os.getenv(config.API_KEY_NAME)),
            "pricing_per_million": {"input": config.PRICE_INPUT_PER_M, "cached_input": config.PRICE_CACHED_INPUT_PER_M,
                                    "output": config.PRICE_OUTPUT_PER_M}}


@app.get("/api/teams")
def list_teams() -> dict:
    return {"league": MLB, "teams": [{**t, "colors": colors(t["team_id"])} for t in teams()]}


@app.get("/api/games")
def list_games(team_id: int, opponent_id: int) -> list[dict]:
    if team_id == opponent_id:
        raise HTTPException(400, "Pick two different teams.")
    return games_between(team_id, opponent_id)


class StartRun(BaseModel):
    game_pk: int
    team_id: int
    notes: str | None = Field(default=None, max_length=1000)


@app.post("/api/runs")
async def start_run(req: StartRun) -> dict:
    active = sum(not r["done"] for r in RUNS.values())
    if active >= MAX_ACTIVE_RUNS:
        raise HTTPException(429, f"{active} plans are already being built. Wait for one to finish.")
    try:
        tools.get_game_context(req.game_pk, req.team_id)      # validates the game and team
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    from backend.agents.team import build_game_plan, new_run_id

    run_id = new_run_id(req.game_pk, req.team_id)
    state = RUNS[run_id] = {"events": [], "done": False, "error": None}

    async def go() -> None:
        try:
            await build_game_plan(req.game_pk, req.team_id, notes=(req.notes or "").strip() or None,
                                  on_event=state["events"].append, run_id=run_id)
        except SystemExit as exc:                               # e.g. missing API key
            state["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - report any failure to the UI instead of hanging
            state["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            state["done"] = True

    state["task"] = asyncio.create_task(go())
    return {"run_id": run_id}


@app.get("/api/runs")
def recent_runs(limit: int = 15) -> list[dict]:
    out = []
    if config.RUNS_DIR.exists():
        for d in sorted(config.RUNS_DIR.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
            f = d / "plan.json"
            if f.exists():
                p = json.loads(f.read_text(encoding="utf-8"))
                out.append({"run_id": d.name, "status": p["status"], "game_date": p["game"]["game_date"],
                            "team": p["game"]["team"], "opponent": p["game"]["opponent"],
                            "cost_usd": p["usage"]["total"]["cost_usd"], "edited": p.get("edited", False)})
            if len(out) >= limit:
                break
    return out


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str, since: int = Query(0, ge=0)) -> dict:
    state = RUNS.get(run_id)
    if state is None:   # e.g. the server restarted: replay from the audit trail on disk
        f = _run_dir(run_id) / "audit.jsonl"
        events = [json.loads(line) for line in f.open(encoding="utf-8")] if f.exists() else []
        state = {"events": events, "done": (f.parent / "plan.json").exists(), "error": None}
    new = [{k: v for k, v in e.items() if k not in LIGHT_FIELDS} for e in state["events"][since:]]
    return {"events": new, "next": since + len(new), "done": state["done"], "error": state["error"]}


@app.get("/api/runs/{run_id}/plan")
def run_plan(run_id: str) -> dict:
    return _plan(run_id)


@app.get("/api/runs/{run_id}/options")
def edit_options(run_id: str) -> dict:
    plan = _plan(run_id)
    g = plan["game"]
    out_ids = {s["player_id"] for s in (plan["sections"].get("medical_report") or {}).get("statuses", [])
               if s["status"] == "out"}
    overview = tools.get_hitters_overview(g["game_pk"], g["team_id"])
    hitters = [{"player_id": h["player_id"], "name": h["name"], "bats": h["bats"], "position": h["position"],
                "starts_by_position": h["starts_by_position"], "xwoba": h["xwoba"]}
               for h in overview if h["player_id"] not in out_ids]
    starters = [s for s in tools.get_starter_options(g["game_pk"], g["team_id"]) if s["player_id"] not in out_ids]
    return {"hitters": hitters, "starters": starters, "roles": ROLES,
            "positions": ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]}


@app.post("/api/runs/{run_id}/edits")
def edit_plan(run_id: str, edits: PlanEdits) -> dict:
    _plan(run_id)
    return apply_edits(_run_dir(run_id), edits)


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@app.get("/api/runs/{run_id}/chat")
def chat_history(run_id: str) -> list[dict]:
    from backend.chat import history

    return history(_run_dir(run_id))


@app.post("/api/runs/{run_id}/chat")
async def chat(run_id: str, msg: ChatMessage) -> dict:
    """Ask the Manager's Assistant to explain or change the plan. Changes are checked by code before saving."""
    from backend.chat import chat_turn

    _plan(run_id)
    try:
        return await chat_turn(_run_dir(run_id), msg.message.strip())
    except SystemExit as exc:                                   # e.g. missing API key
        raise HTTPException(503, str(exc)) from exc


@app.get("/api/runs/{run_id}/export")
def export(run_id: str) -> Response:
    from backend.agents.team import PACKETS

    plan = _plan(run_id)
    g = plan["game"]
    name = f"game-plan_{g['game_date']}_{plan['run_id'].split('_')[1]}.zip"
    return Response(export_zip(plan, PACKETS), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --- the React app ------------------------------------------------------------------
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str) -> Response:
    if path.startswith("api/"):
        raise HTTPException(404, "Unknown API route.")
    target = DIST / path
    if path and target.is_file() and DIST in target.resolve().parents:
        return FileResponse(target)
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return Response("The web app has not been built. Run: cd frontend && npm install && npm run build",
                    media_type="text/plain", status_code=503)
