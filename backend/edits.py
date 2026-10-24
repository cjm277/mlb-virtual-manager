"""Apply the human manager's edits to a finished plan, then re-check it with the same consistency checker.

Edits arrive two ways: the dropdowns on the review screen, or the chat assistant (backend/chat.py), which
turns a request like "I don't like Clement in this matchup" into the same structured PlanEdits. Either
way the change is applied here in code and re-checked against the rules and the run's tool ledger.
Every change is recorded in the plan's edit_log, and the original plan is kept as plan_original.json.
"""

from __future__ import annotations

import copy
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from backend.checker import check_plan
from backend.engine.roster import player_info
from backend.models import (HittersScoutingReport, LineupPlan, MedicalReport, PitchersScoutingReport, PitchingPlan,
                            Position)

ROLES = ["closer", "setup", "middle", "long", "lefty_specialist", "mop_up", "unavailable"]


class LineupEdit(BaseModel):
    slot: int
    player_id: int
    position: Position
    reason: str | None = Field(default=None, description="Why this player is here (only for changed spots).")


class PlanEdits(BaseModel):
    lineup: list[LineupEdit] | None = None
    starter_id: int | None = None
    bullpen_roles: dict[int, str] | None = None
    staff_notes: str | None = Field(default=None, max_length=2000)


def _models(plan: dict) -> dict:
    s = plan["sections"]
    load = lambda cls, key: cls.model_validate(s[key]) if s.get(key) else None  # noqa: E731
    return {"medical": load(MedicalReport, "medical_report"),
            "scout_pitchers": load(PitchersScoutingReport, "opposing_pitchers_report"),
            "scout_hitters": load(HittersScoutingReport, "opposing_hitters_report"),
            "pitching": load(PitchingPlan, "pitching_plan"), "lineup": load(LineupPlan, "lineup_card")}


def load_ledger(run_dir: Path) -> list[Any] | None:
    f = run_dir / "ledger.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def recheck(plan: dict, ledger: list[Any] | None) -> list[dict]:
    g = plan["game"]
    issues = check_plan(g["game_pk"], g["team_id"], g["opponent_id"], ledger=ledger or [], **_models(plan))
    if ledger is None:   # plans saved before ledgers were kept: rules are re-checked, numbers can't be
        issues = [i for i in issues if i.code != "unsupported_number"]
    return [i.as_dict() for i in issues]


def apply_to_plan(plan: dict, edits: PlanEdits, source: str = "manager") -> tuple[dict, list[str]]:
    """Apply edits to a COPY of the plan. Returns (new plan, list of changes in plain English)."""
    plan = copy.deepcopy(plan)
    s = plan["sections"]
    log: list[str] = []
    who = "the manager" if source == "manager" else "the chat assistant, at the manager's request"

    if edits.lineup is not None and s.get("lineup_card"):
        card = s["lineup_card"]
        old = {sp["player_id"]: sp for sp in card["lineup"]}
        new_ids = {e.player_id for e in edits.lineup}
        spots = []
        for e in sorted(edits.lineup, key=lambda x: x.slot):
            info = player_info(e.player_id) or {}
            prev = old.get(e.player_id)
            same = prev and prev["slot"] == e.slot and prev["position"] == e.position
            if not same:
                log.append(f"Slot {e.slot}: {info.get('full_name')} at {e.position}")
            reason = (prev["reason"] if same else e.reason or f"Set by {who}.")
            spots.append({"slot": e.slot, "player_id": e.player_id, "name": info.get("full_name"),
                          "position": e.position, "bats": info.get("bat_side") or "R", "reason": reason})
        bench = [b for b in card["bench"] if b["player_id"] not in new_ids]
        for pid in old.keys() - new_ids:
            bench.append({"player_id": pid, "name": old[pid]["name"], "role": "utility",
                          "note": f"Moved to the bench by {who}."})
            log.append(f"{old[pid]['name']} moved to the bench")
        bench_ids = {b["player_id"] for b in bench}
        kept = []
        for sub in card["substitutions"]:
            if sub["bench_player_id"] in bench_ids and sub["replaces_player_id"] in new_ids:
                kept.append(sub)
            else:
                log.append(f"Dropped planned move '{sub['situation']}' (its players changed)")
        card.update(lineup=spots, bench=bench, substitutions=kept)

    if edits.starter_id is not None and s.get("pitching_plan"):
        pp = s["pitching_plan"]
        if edits.starter_id != pp["starter"]["player_id"]:
            info = player_info(edits.starter_id) or {}
            old_name = pp["starter"]["name"]
            pp["starter"].update(player_id=edits.starter_id, name=info.get("full_name"),
                                 throws=info.get("pitch_hand") or "R",
                                 reason=f"Chosen by {who} (the staff recommended {old_name}).")
            pp["starter"]["plan_written_for"] = old_name
            pp["bullpen"] = [b for b in pp["bullpen"] if b["player_id"] != edits.starter_id]
            for sc in pp["scenarios"]:
                sc["pitcher_ids"] = [p for p in sc["pitcher_ids"] if p != edits.starter_id]
            log.append(f"Starter changed to {info.get('full_name')} (pitch mix and keys were written for {old_name})")

    if edits.bullpen_roles and s.get("pitching_plan"):
        for b in s["pitching_plan"]["bullpen"]:
            role = edits.bullpen_roles.get(b["player_id"])
            if role and role in ROLES and role != b["role"]:
                log.append(f"{b['name']}: {b['role']} -> {role}")
                b["role"] = role

    if edits.staff_notes is not None and edits.staff_notes.strip() != (plan.get("staff_notes") or ""):
        plan["staff_notes"] = edits.staff_notes.strip()
        log.append("Staff notes updated")
    return plan, log


def save(run_dir: Path, plan: dict, log: list[str], issues: list[dict], source: str = "manager") -> dict:
    if not (run_dir / "plan_original.json").exists():
        shutil.copy(run_dir / "plan.json", run_dir / "plan_original.json")
    if log:
        plan.setdefault("edit_log", []).append({"at": datetime.now().isoformat(timespec="seconds"),
                                                "source": source, "changes": log})
    plan["checker"]["open_issues"] = issues
    plan["checker"]["rechecked_after_edit"] = True
    plan["edited"] = bool(plan.get("edit_log"))
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
    return plan


def apply_edits(run_dir: Path, edits: PlanEdits) -> dict:
    """Dropdown edits: apply, re-check, and save (even with issues, which the review screen then shows)."""
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    plan, log = apply_to_plan(plan, edits)
    return save(run_dir, plan, log, recheck(plan, load_ledger(run_dir)))
