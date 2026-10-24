"""Spending guards across runs: a daily dollar cap, and reuse of a plan already built for the same request.

Per-run caps (requests, tool calls, tokens, steps per agent, fix rounds) live in config.py and stop one
runaway plan. These guards stop the other kind of overspending: someone clicking "Build" over and over.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

from backend import config


def _run_cost(run_dir: Path) -> float:
    plan = run_dir / "plan.json"
    if plan.exists():
        usage = json.loads(plan.read_text(encoding="utf-8"))["usage"]
        return usage["total"]["cost_usd"] + (usage.get("chat") or {}).get("cost_usd", 0)
    audit = run_dir / "audit.jsonl"           # still building: count what it has spent so far
    if not audit.exists():
        return 0.0
    return sum(e.get("cost_usd", 0) for e in map(json.loads, audit.open(encoding="utf-8")) if e["event"] == "model_step")


def spent_today(runs_dir: Path | None = None) -> float:
    """List-price dollars spent today (local time) on plans and chat."""
    runs_dir = runs_dir or config.RUNS_DIR
    if not runs_dir.exists():
        return 0.0
    today = date.today()
    return round(sum(_run_cost(d) for d in runs_dir.iterdir()
                     if d.is_dir() and datetime.fromtimestamp(d.stat().st_mtime).date() == today), 4)


def over_daily_cap(runs_dir: Path | None = None) -> str | None:
    spent = spent_today(runs_dir)
    if spent >= config.DAILY_BUDGET_USD:
        return (f"Today's spending cap of ${config.DAILY_BUDGET_USD:.2f} has been reached (${spent:.2f} spent). "
                "Saved plans still open and edit for free; new builds and chat resume tomorrow.")
    return None


def existing_plan(game_pk: int, team_id: int, notes: str | None, runs_dir: Path | None = None) -> str | None:
    """The newest finished plan for exactly this request (same game, team and notes) from the last 24 hours."""
    runs_dir = runs_dir or config.RUNS_DIR
    if not runs_dir.exists():
        return None
    cutoff = time.time() - config.REUSE_HOURS * 3600
    for d in sorted(runs_dir.iterdir(), key=lambda d: d.stat().st_mtime, reverse=True):
        f = d / "plan.json"
        if not f.exists() or d.stat().st_mtime < cutoff:
            continue
        p = json.loads(f.read_text(encoding="utf-8"))
        if (p["game"]["game_pk"] == game_pk and p["game"]["team_id"] == team_id
                and (p.get("manager_notes") or None) == (notes or None)
                and p["status"] in ("approved", "needs_human_review")):
            return d.name
    return None
