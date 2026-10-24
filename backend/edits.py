"""Apply the human manager's edits to a finished plan, then re-check it with the same consistency checker.

No model calls: edits are applied in code and checked against the rules and the run's tool ledger.
Every change is recorded in the plan's edit_log, and the original plan is kept as plan_original.json.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

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


def recheck(plan: dict, run_dir: Path) -> list[dict]:
    ledger_file = run_dir / "ledger.json"
    ledger = json.loads(ledger_file.read_text(encoding="utf-8")) if ledger_file.exists() else []
    m = _models(plan)
    g = plan["game"]
    issues = check_plan(g["game_pk"], g["team_id"], g["opponent_id"], ledger=ledger, **m)
    if not ledger_file.exists():   # plans saved before ledgers were kept: rules are re-checked, numbers can't be
        issues = [i for i in issues if i.code != "unsupported_number"]
    return [i.as_dict() for i in issues]


def apply_edits(run_dir: Path, edits: PlanEdits) -> dict:
    plan_file = run_dir / "plan.json"
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    if not (run_dir / "plan_original.json").exists():
        shutil.copy(plan_file, run_dir / "plan_original.json")
    s = plan["sections"]
    log: list[str] = []

    if edits.lineup is not None and s.get("lineup_card"):
        card = s["lineup_card"]
        old = {sp["player_id"]: sp for sp in card["lineup"]}
        new_ids = {e.player_id for e in edits.lineup}
        spots = []
        for e in sorted(edits.lineup, key=lambda x: x.slot):
            info = player_info(e.player_id) or {}
            prev = old.get(e.player_id)
            if not prev or prev["slot"] != e.slot or prev["position"] != e.position:
                log.append(f"Slot {e.slot}: {info.get('full_name')} at {e.position}")
            spots.append({"slot": e.slot, "player_id": e.player_id, "name": info.get("full_name"),
                          "position": e.position, "bats": info.get("bat_side") or "R",
                          "reason": prev["reason"] if prev and prev["slot"] == e.slot else "Set by the manager."})
        bench = [b for b in card["bench"] if b["player_id"] not in new_ids]
        for pid in old.keys() - new_ids:
            bench.append({"player_id": pid, "name": old[pid]["name"], "role": "utility",
                          "note": "Moved to the bench by the manager."})
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
                                 reason=f"Chosen by the manager (the staff recommended {old_name}).")
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

    if edits.staff_notes is not None:
        plan["staff_notes"] = edits.staff_notes.strip()
        log.append("Staff notes updated")

    if log:
        plan.setdefault("edit_log", []).append({"at": datetime.now().isoformat(timespec="seconds"), "changes": log})
    issues = recheck(plan, run_dir)
    plan["checker"]["open_issues"] = issues
    plan["checker"]["rechecked_after_edit"] = True
    plan["edited"] = bool(plan.get("edit_log"))
    plan_file.write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
    return plan
