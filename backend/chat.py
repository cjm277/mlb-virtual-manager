"""Chat editing: the manager types a request, the Manager's Assistant agent turns it into a structured edit.

Flow for one message:
  1. The assistant reads the current plan, who is available, and the conversation so far, and may call the
     same data tools as the staff.
  2. Its reply becomes the same PlanEdits the dropdowns produce (it can change nothing else).
  3. The edit is applied to a COPY of the plan and run through the consistency checker, and every number in
     the reply is checked against tool results.
  4. If anything fails, the assistant sees the problems and gets one chance to correct its change.
  5. Only a change that passes is saved. Otherwise the plan is untouched and the manager is told why.
Every step is appended to the run's audit trail (events marked "chat"), and token use and cost are added to
the plan under usage.chat.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage

from backend import tools
from backend.agents.team import AgentStepLimit, Tally, run_agent
from backend.agents.toolkit import PlanDeps
from backend.audit import Audit
from backend.checker import check_numbers, ledger_numbers
from backend.edits import LineupEdit, PlanEdits, apply_to_plan, load_ledger, recheck, save
from backend.models import ChatReply

HISTORY_TURNS = 6


def history(run_dir: Path) -> list[dict]:
    f = run_dir / "chat.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else []


def _to_edits(reply: ChatReply) -> PlanEdits:
    return PlanEdits(
        lineup=[LineupEdit(slot=s.slot, player_id=s.player_id, position=s.position, reason=s.reason)
                for s in reply.lineup] if reply.lineup else None,
        starter_id=reply.starter_id,
        bullpen_roles={r.player_id: r.role for r in reply.bullpen_roles} if reply.bullpen_roles else None,
    )


def _state(plan: dict) -> str:
    """The plan as the assistant needs to see it: compact, ids included."""
    s, g = plan["sections"], plan["game"]
    lc, pp = s.get("lineup_card") or {}, s.get("pitching_plan") or {}
    out = [s2["name"] + f" ({s2['player_id']})" for s2 in (s.get("medical_report") or {}).get("statuses", [])
           if s2["status"] == "out"]
    available = [{"player_id": h["player_id"], "name": h["name"], "bats": h["bats"],
                  "starts_by_position": h["starts_by_position"]}
                 for h in tools.get_hitters_overview(g["game_pk"], g["team_id"])]
    return json.dumps({
        "opposing_starter_assumed": lc.get("opposing_starter_assumed"),
        "current_lineup": [{k: x[k] for k in ("slot", "player_id", "name", "position", "bats")}
                           for x in sorted(lc.get("lineup", []), key=lambda x: x["slot"])],
        "bench": [{k: x[k] for k in ("player_id", "name", "role")} for x in lc.get("bench", [])],
        "starter": {k: pp["starter"][k] for k in ("player_id", "name", "throws")} if pp else None,
        "bullpen": [{k: x[k] for k in ("player_id", "name", "throws", "role")} for x in pp.get("bullpen", [])],
        "out_per_team_doctor": out,
        "available_hitters": available,
        "staff_notes": plan.get("staff_notes"),
    })


async def chat_turn(run_dir: Path, message: str) -> dict:
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    g = plan["game"]
    audit = Audit(run_dir)
    run_ledger = load_ledger(run_dir)
    deps = PlanDeps(game_pk=g["game_pk"], team_id=g["team_id"], opponent_id=g["opponent_id"],
                    game_date=g["game_date"], audit=audit, context=g, ledger=list(run_ledger or []))
    usage, tally = RunUsage(), Tally()
    past = history(run_dir)[-HISTORY_TURNS:]
    convo = "\n".join(f"{t['role']}: {t['text']}" for t in past) or "(none)"
    audit.log("chat_message", message=message)
    task = (f"Current plan (JSON): {_state(plan)}\n\nConversation so far:\n{convo}\n\n"
            f"The manager now says:\n<manager_message>\n{message}\n</manager_message>")

    status, applied, issues, reply = "answered", [], [], None
    try:
        reply = await run_agent("assistant", task, deps, usage, tally)
        for attempt in range(2):
            new_plan, log = apply_to_plan(plan, _to_edits(reply), source="chat")
            if reply.staff_note:
                note = ((new_plan.get("staff_notes") or "") + "\n" + reply.staff_note.strip()).strip()
                new_plan["staff_notes"] = note
                log.append("Staff note added")
            # A change must leave the whole plan passing the checker; a pure answer only has its numbers checked.
            issues = recheck(new_plan, deps.ledger if run_ledger is not None else None) if log else []
            issues += [i.as_dict() for i in check_numbers("assistant", reply, ledger_numbers(deps.ledger))]
            audit.log("chat_check", attempt=attempt, changes=log, passed=not issues, issues=issues)
            if not issues:
                if log:
                    plan = save(run_dir, new_plan, log, [], source="chat")
                    applied, status = log, "changed"
                break
            if attempt == 0:
                problems = "\n".join(f"- {i['message']}" for i in issues)
                reply = await run_agent("assistant", f"{task}\n\nYour proposed change was NOT saved because:\n{problems}\n"
                                        f"Your previous reply: {reply.model_dump_json()}\n"
                                        "Return a corrected reply (or change nothing and explain).", deps, usage, tally)
            else:
                status = "rejected"
    except (UsageLimitExceeded, AgentStepLimit) as exc:
        status, issues = "stopped_by_budget", [{"owner": "assistant", "code": "budget", "message": str(exc)}]

    text = reply.message if reply else "Sorry, I couldn't finish that request within the budget."
    if status == "rejected":
        text += " (I couldn't make a change that passes the plan's rules, so nothing was changed.)"
    # Usage for chat is tracked separately from the build.
    t = tally.total()
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    chat_usage = plan["usage"].setdefault("chat", {k: 0 for k in t})
    for k, v in t.items():
        chat_usage[k] = round(chat_usage.get(k, 0) + v, 6)
    (run_dir / "plan.json").write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")

    turns = history(run_dir)
    now = datetime.now().isoformat(timespec="seconds")
    turns += [{"role": "manager", "text": message, "at": now},
              {"role": "assistant", "text": text, "at": now, "status": status, "changes": applied,
               "issues": issues, "cost_usd": t["cost_usd"]}]
    (run_dir / "chat.json").write_text(json.dumps(turns, indent=2), encoding="utf-8")
    audit.log("chat_reply", status=status, changes=applied, issues=issues, usage=t)
    return {"reply": text, "status": status, "changes": applied, "issues": issues, "plan": plan, "history": turns}
