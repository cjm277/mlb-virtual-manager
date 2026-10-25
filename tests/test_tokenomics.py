"""Phase 8 cost cutters: compact matchups keep every number, and the self-check fixes a rule break inside the
agent's own loop (one extra step) without ever crashing a run. No real model is called."""

import asyncio
import json
from pathlib import Path

from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage

from backend import config, tools
from backend.agents import team
from backend.agents.toolkit import PlanDeps, compact_matchups
from backend.audit import Audit
from backend.checker import ledger_numbers
from backend.models import LineupPlan, MedicalReport, PitchersScoutingReport

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / "evidence" / "logs" / "phase5_ui_run_2027"     # a real, approved 2027 plan
PLAN = json.loads((SAVED / "plan.json").read_text(encoding="utf-8"))
G = PLAN["game"]
S = PLAN["sections"]


def test_compact_matchups_keep_every_number_in_fewer_characters():
    rows = tools.get_matchups(G["game_pk"], S["pitching_plan"]["starter"]["player_id"],
                              [h["player_id"] for h in S["opposing_hitters_report"]["lineup_vs_rhp"]])
    compact = compact_matchups(rows)
    assert ledger_numbers(compact) == ledger_numbers(rows)            # nothing the checker can verify is lost
    assert len(compact["batters"]) == len(rows)
    assert [b["batter_id"] for b in compact["batters"]] == [r["batter_id"] for r in rows]   # still best-first
    assert len(json.dumps(compact)) < 0.75 * len(json.dumps(rows))


def bench_run(tmp_path, responses):
    """Run the Bench Coach on a scripted model that hands in each lineup in turn; return (output, calls, audit)."""
    calls = []

    def fake(messages, info: AgentInfo):
        out = responses[min(len(calls), len(responses) - 1)]
        calls.append(out)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out.model_dump())])

    r = {"medical": MedicalReport.model_validate(S["medical_report"]),
         "scout_pitchers": PitchersScoutingReport.model_validate(S["opposing_pitchers_report"])}
    ledger = json.loads((SAVED / "ledger.json").read_text(encoding="utf-8"))
    audit = Audit(tmp_path / "run")
    d = PlanDeps(game_pk=G["game_pk"], team_id=G["team_id"], opponent_id=G["opponent_id"], game_date=G["game_date"],
                 audit=audit, context=G, ledger=ledger,
                 self_check=team.make_self_check(G["game_pk"], G["team_id"], G["opponent_id"], r, ledger))
    with team.build_agent("bench_coach").override(model=FunctionModel(fake)):
        out = asyncio.run(team.run_agent("bench_coach", "Build the lineup.", d, RunUsage(), team.Tally()))
    events = [json.loads(line) for line in (tmp_path / "run" / "audit.jsonl").open(encoding="utf-8")]
    return out, calls, [e for e in events if e["event"] == "self_check"]


def double_booked() -> LineupPlan:
    bad = LineupPlan.model_validate(S["lineup_card"])
    bad.lineup[1].position = bad.lineup[0].position
    return bad


def test_self_check_sends_a_double_booked_lineup_back_to_the_bench_coach(tmp_path):
    good = LineupPlan.model_validate(S["lineup_card"])
    out, calls, checks = bench_run(tmp_path, [double_booked(), good])
    assert len(calls) == 2                                   # one extra step inside the agent, not a fix round
    assert out == good
    assert "Each position must be filled once" in checks[0]["issues"][0]


def test_self_check_gives_up_after_one_retry_and_leaves_it_to_the_fix_loop(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SELF_CHECK_RETRIES", 1)
    out, calls, checks = bench_run(tmp_path, [double_booked()])
    assert len(calls) == 2 and len(checks) == 1              # no crash: the run continues and the checker catches it
    assert out == double_booked()


def test_self_check_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SELF_CHECK_RETRIES", 0)
    out, calls, checks = bench_run(tmp_path, [double_booked()])
    assert len(calls) == 1 and not checks
