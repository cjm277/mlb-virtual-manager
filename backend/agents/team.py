"""The seven-agent staff and the run that turns one game into one game plan.

Run order (fixed in code, so it is predictable and cheap):
  1. Team Doctor            who is out or limited
  2. Scouts, in parallel    opposing pitchers (for our hitters) and opposing hitters (for our pitchers)
  3. Coaches, in parallel   Pitching Coach (starter, pitch mix, bullpen, scenarios) and Bench Coach (lineup, bench, moves)
  4. Consistency checker    plain code: plan rules + every quoted stat must match a tool result
  5. Manager review         approves, or sends fixes to the coach/scout who owns each problem
  6. Fix loop               the named agents redo their part with the problems spelled out (max 2 rounds)
  7. Clubhouse Comms        one briefing each for hitters, pitchers, coaches
Packets for each audience are then assembled by code from a fixed allowlist of sections.

Every agent step, tool call, token count (input, cached input, output), timing and cost is appended to
runs/<run_id>/audit.jsonl, and the finished plan is saved to runs/<run_id>/plan.json.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import lru_cache
from typing import Any, Callable

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import BaseToolCallPart, TextPart
from pydantic_ai.usage import RunUsage

from backend import config, tools
from backend.agents import toolkit as tk
from backend.agents.toolkit import PlanDeps
from backend.audit import Audit, preview
from backend.checker import Issue, check_briefing_leaks, check_numbers, check_plan, check_prompt_leak, ledger_numbers
from backend.engine.games import team as team_info
from backend.models import (ChatReply, CommsPackage, HittersScoutingReport, LineupPlan, ManagerReview,
                            MedicalReport, PitchersScoutingReport, PitchingPlan)


@dataclass(frozen=True)
class Spec:
    title: str
    output: type[BaseModel]
    tools: tuple[str, ...]


SPECS: dict[str, Spec] = {
    "team_doctor": Spec("Team Doctor", MedicalReport, ("roster_and_injuries", "bullpen_status")),
    "scout_pitchers": Spec("Advance Scout (pitchers)", PitchersScoutingReport,
                           ("predict_opponent_starter", "pitcher_profile", "hitters_overview", "matchups",
                            "bullpen_status")),
    "scout_hitters": Spec("Advance Scout (hitters)", HittersScoutingReport,
                          ("predict_opponent_lineup", "hitters_overview", "hitter_profile")),
    "pitching_coach": Spec("Pitching Coach", PitchingPlan,
                           ("starter_options", "pitcher_profile", "bullpen_status", "matchups")),
    "bench_coach": Spec("Bench Coach", LineupPlan, ("model_lineup", "hitters_overview", "hitter_profile", "matchups")),
    "manager": Spec("Manager", ManagerReview, ()),
    "clubhouse_comms": Spec("Clubhouse Comms", CommsPackage, ()),
    # Not part of the build: the chat assistant that edits a finished plan (backend/chat.py).
    "assistant": Spec("Manager's Assistant", ChatReply,
                      ("hitters_overview", "hitter_profile", "matchups", "starter_options", "bullpen_status",
                       "pitcher_profile")),
}
FIXABLE = {"pitching_coach", "bench_coach", "scout_pitchers", "scout_hitters"}

# What each audience's packet may contain. Enforced here in code, not left to an agent.
PACKETS = {
    "hitters": ["lineup_card", "opposing_pitchers_report", "hitters_briefing"],
    "pitchers": ["pitching_plan", "opposing_hitters_report", "pitchers_briefing"],
    "coaches": ["lineup_card", "pitching_plan", "opposing_pitchers_report", "opposing_hitters_report",
                "medical_report", "manager_review", "hitters_briefing", "pitchers_briefing", "coaches_briefing"],
}


NOTES_MAX = 1000


def clean_notes(notes: str) -> str:
    """Manager notes are data: cap the length and strip anything tag-like, so a note can't close the
    <manager_notes> block and pose as instructions."""
    return re.sub(r"<[^>]*>", "", notes)[:NOTES_MAX].strip()


class AgentStepLimit(RuntimeError):
    pass


def _prompt(name: str) -> str:
    return (config.PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def build_agent(name: str) -> Agent:
    spec = SPECS[name]
    agent = Agent(
        config.build_model(),
        name=name,
        output_type=spec.output,
        deps_type=PlanDeps,
        instructions=[_prompt("shared_rules"), _prompt(name)],   # static first, so the prefix can be cached
        tools=[tk.ALL_TOOLS[t] for t in spec.tools],
        model_settings=config.model_settings(),
        retries=2,
    )

    @agent.instructions
    def game_facts(ctx: RunContext[PlanDeps]) -> str:
        c = ctx.deps.context
        lines = [
            f"Game: {c['team']} ({c['home_away']}) vs {c['opponent']} on {c['game_date']} at {c['venue']}.",
            f"Our team_id is {c['team_id']}; the opponent's team_id is {c['opponent_id']}.",
            f"Stats basis: {c['stats_basis']}",
        ]
        if c.get("roster_basis"):
            lines.append(f"Roster basis: {c['roster_basis']}")
        if ctx.deps.notes:
            lines.append(f"<manager_notes>\n{clean_notes(ctx.deps.notes)}\n</manager_notes>")
        return "\n".join(lines)

    if name in FIXABLE:
        @agent.output_validator
        def self_check(ctx: RunContext[PlanDeps], output: Any) -> Any:
            """Run the code checker on this agent's part before it is handed in. A rule break goes back to the
            same agent as a retry (one more step in its own loop) instead of costing a whole fix round."""
            check = ctx.deps.self_check
            if check is None or ctx.retry >= min(config.SELF_CHECK_RETRIES, ctx.max_retries - 1):
                return output
            problems = check(name, output)
            if problems:
                ctx.deps.audit.log("self_check", agent=name, retry=ctx.retry, issues=problems)
                bullets = "\n".join(f"- {p}" for p in problems)
                raise ModelRetry(f"The code checker found problems in your output:\n{bullets}\n"
                                 "Fix them and return the complete corrected output.")
            return output

    return agent


# ---------------------------------------------------------------------------
# One audited agent loop
# ---------------------------------------------------------------------------

EMPTY = {"calls": 0, "model_steps": 0, "gateway_cache_hits": 0, "input_tokens": 0, "cached_tokens": 0,
         "output_tokens": 0, "seconds": 0.0, "cost_usd": 0.0}


@dataclass
class Tally:
    """Running totals for the whole run and for each agent."""
    by_agent: dict[str, dict] = field(default_factory=dict)

    def add(self, agent: str, inp: int, cached: int, out: int, gateway_cache_hit: bool = False) -> None:
        a = self.by_agent.setdefault(agent, dict(EMPTY))
        a["model_steps"] += 1
        a["gateway_cache_hits"] += gateway_cache_hit
        a["input_tokens"] += inp
        a["cached_tokens"] += cached
        a["output_tokens"] += out
        # A Portkey cache hit is answered by the gateway, not the model, so it is not billed.
        a["cost_usd"] += 0.0 if gateway_cache_hit else config.cost_usd(inp, cached, out)

    def total(self) -> dict:
        keys = ("model_steps", "gateway_cache_hits", "input_tokens", "cached_tokens", "output_tokens", "cost_usd")
        t = {k: sum(a[k] for a in self.by_agent.values()) for k in keys}
        t["cost_usd"] = round(t["cost_usd"], 5)
        return t


async def run_agent(name: str, task: str, deps: PlanDeps, usage: RunUsage, tally: Tally) -> Any:
    agent = build_agent(name)
    d = replace(deps, agent=name)
    audit = deps.audit
    audit.log("agent_start", agent=name, title=SPECS[name].title, task=preview(task, 1500))
    started = time.perf_counter()
    sent = started
    step = 0
    a = tally.by_agent.setdefault(name, dict(EMPTY))
    a["calls"] += 1

    async def loop() -> Any:
        nonlocal step, sent
        gateway: list = []
        config.GATEWAY_LOG.set(gateway)
        async with agent.iter(task, deps=d, usage=usage, usage_limits=config.run_limits()) as run:
            async for node in run:
                if Agent.is_model_request_node(node):
                    sent = time.perf_counter()
                elif Agent.is_call_tools_node(node):
                    step += 1
                    resp = node.model_response
                    u = resp.usage
                    inp, cached, out = u.input_tokens or 0, u.cache_read_tokens or 0, u.output_tokens or 0
                    secs = time.perf_counter() - sent
                    gw = gateway[-1] if gateway else {}
                    tally.add(name, inp, cached, out, gateway_cache_hit=gw.get("cache") == "HIT")
                    audit.log("model_step", agent=name, step=step, seconds=round(secs, 2),
                              gateway_cache=gw.get("cache"), provider=gw.get("provider"),
                              input_tokens=inp, cached_tokens=cached, output_tokens=out,
                              cost_usd=0.0 if gw.get("cache") == "HIT" else round(config.cost_usd(inp, cached, out), 6),
                              tool_calls=[{"tool": p.tool_name, "args": p.args_as_dict()}
                                          for p in resp.parts if isinstance(p, BaseToolCallPart)],
                              text=[preview(p.content, 400) for p in resp.parts if isinstance(p, TextPart) and p.content],
                              finish_reason=resp.finish_reason,
                              run_requests_so_far=usage.requests, run_tokens_so_far=usage.total_tokens)
                    if step >= config.MAX_STEPS_PER_AGENT:
                        raise AgentStepLimit(f"{name} hit the {config.MAX_STEPS_PER_AGENT}-step limit")
            return run.result.output

    try:
        output = await asyncio.wait_for(loop(), timeout=config.AGENT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        audit.log("agent_error", agent=name, error=f"timed out after {config.AGENT_TIMEOUT_SECONDS}s")
        raise AgentStepLimit(f"{name} timed out") from exc
    secs = time.perf_counter() - started
    a["seconds"] += secs
    audit.log("agent_end", agent=name, seconds=round(secs, 2), steps=step, output=preview(output.model_dump(), 3000))
    return output


# ---------------------------------------------------------------------------
# Task prompts (upstream reports are passed in as JSON data)
# ---------------------------------------------------------------------------

def stamp_probability(report: PitchersScoutingReport | None, ctx: dict) -> None:
    """Attach the starter predictor's historical hit rate to the scout's pick (set by code, never by the model)."""
    if report is None:
        return
    from backend.engine.rotation import predict_starter

    pred = predict_starter(ctx["opponent_id"], ctx["game_date"], ctx["game_number"])
    sp = report.opposing_starter
    prob = pred.get("probability")
    if pred["predicted"] and pred["predicted"]["player_id"] == sp.player_id and prob:
        sp.probability_pct, sp.probability_basis = prob["pct"], prob["basis"]
    else:
        sp.probability_pct = None
        sp.probability_basis = "The scout picked someone other than the rotation model's choice, so no track record applies."


def stamp_rest_days(medical: MedicalReport | None, ctx: dict) -> None:
    """Make sure every hitter past the rest-day threshold is in the medical report (added by code if the
    Team Doctor missed him), so the Bench Coach and the human always see the workload flag."""
    if medical is None:
        return
    from backend.models import PlayerStatus

    roster = tools.get_roster_and_injuries(ctx["game_pk"], ctx["team_id"])
    tired = {h["player_id"]: h for h in roster["hitters"] if h.get("rest_suggested")}
    # Fatigue is never "out" for a hitter: tired is the manager's call, injured is not.
    for s in medical.statuses:
        if s.status == "out" and s.player_id in tired:
            s.status, s.reason = "rest_suggested", tired[s.player_id]["rest_note"]
    listed = {s.player_id for s in medical.statuses}
    for h in roster["hitters"]:
        if h.get("rest_suggested") and h["player_id"] not in listed:
            medical.statuses.append(PlayerStatus(player_id=h["player_id"], name=h["name"], status="rest_suggested",
                                                 reason=h["rest_note"]))


def _j(model: BaseModel | None) -> str:
    return model.model_dump_json(exclude_none=True) if model else "null"


def _fix_task(base: str, previous: BaseModel, problems: list[str]) -> str:
    bullets = "\n".join(f"- {p}" for p in problems)
    return (f"{base}\n\nYour previous version had problems that must be fixed:\n{bullets}\n\n"
            f"Your previous version (JSON):\n{_j(previous)}\n\n"
            "Return a complete corrected version. Re-check tools if you need to.")


def _tasks(r: dict) -> dict[str, str]:
    medical = _j(r.get("medical"))
    return {
        "team_doctor": "Report who on our team is out, limited, or cleared with caution for this game.",
        "scout_pitchers": f"Scout the opponent's pitchers for our hitters.\nTeam Doctor report: {medical}",
        "scout_hitters": "Scout the opponent's hitters for our pitchers.",
        "pitching_coach": (f"Build our pitching plan.\nTeam Doctor report: {medical}\n"
                           f"Opposing hitters scouting report: {_j(r.get('scout_hitters'))}"),
        "bench_coach": (f"Build our lineup, bench, and moves.\nTeam Doctor report: {medical}\n"
                        f"Opposing pitchers scouting report: {_j(r.get('scout_pitchers'))}"),
    }


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------

RESULT_KEY = {"team_doctor": "medical", "scout_pitchers": "scout_pitchers", "scout_hitters": "scout_hitters",
              "pitching_coach": "pitching", "bench_coach": "lineup"}


def make_self_check(game_pk: int, team_id: int, opponent_id: int, r: dict, ledger: list) -> Callable[[str, Any], list[str]]:
    """The checker's problems with one agent's output, judged against what that agent was given (the Team
    Doctor's report, plus the scouts' predicted starter for the Bench Coach)."""
    def self_check(name: str, output: BaseModel) -> list[str]:
        parts = {"medical": r["medical"], "scout_pitchers": r["scout_pitchers"] if name == "bench_coach" else None,
                 "scout_hitters": None, "pitching": None, "lineup": None}
        parts[RESULT_KEY[name]] = output
        return [i.message for i in check_plan(game_pk, team_id, opponent_id, ledger=ledger, **parts) if i.owner == name]
    return self_check


def new_run_id(game_pk: int, team_id: int) -> str:
    ctx = tools.get_game_context(game_pk, team_id)
    our, opp = team_info(team_id)["abbrev"], team_info(ctx["opponent_id"])["abbrev"]
    return f"{ctx['game_date']}_{our}-vs-{opp}_{datetime.now():%Y%m%d-%H%M%S}"


async def build_game_plan(game_pk: int, team_id: int, notes: str | None = None,
                          on_event: Callable[[dict], None] | None = None, run_id: str | None = None) -> dict:
    ctx = tools.get_game_context(game_pk, team_id)
    run_id = run_id or new_run_id(game_pk, team_id)
    audit = Audit(config.RUNS_DIR / run_id, on_event)
    deps = PlanDeps(game_pk=game_pk, team_id=team_id, opponent_id=ctx["opponent_id"], game_date=ctx["game_date"],
                    audit=audit, context=ctx, notes=notes)
    usage, tally = RunUsage(), Tally()
    started = time.perf_counter()
    audit.log("run_start", run_id=run_id, game=ctx, notes=notes, model=config.MODEL_NAME,
              limits={"requests": config.MAX_REQUESTS_PER_RUN, "tool_calls": config.MAX_TOOL_CALLS_PER_RUN,
                      "tokens": config.MAX_TOKENS_PER_RUN, "steps_per_agent": config.MAX_STEPS_PER_AGENT,
                      "fix_rounds": config.MAX_FIX_ROUNDS},
              pricing={"input_per_m": config.PRICE_INPUT_PER_M, "cached_per_m": config.PRICE_CACHED_INPUT_PER_M,
                       "output_per_m": config.PRICE_OUTPUT_PER_M, "source": config.PRICE_SOURCE})

    r: dict[str, Any] = {"medical": None, "scout_pitchers": None, "scout_hitters": None,
                         "pitching": None, "lineup": None, "review": None, "comms": None}
    key = RESULT_KEY
    issues: list[Issue] = []
    status, rounds = "incomplete", 0

    async def call(name: str, task: str) -> Any:
        return await run_agent(name, task, deps, usage, tally)

    if config.SELF_CHECK_RETRIES > 0:
        deps.self_check = make_self_check(game_pk, team_id, ctx["opponent_id"], r, deps.ledger)

    try:
        r["medical"] = await call("team_doctor", _tasks(r)["team_doctor"])
        stamp_rest_days(r["medical"], ctx)
        deps.unavailable = {s.player_id for s in r["medical"].statuses if s.status == "out"}
        r["scout_pitchers"], r["scout_hitters"] = await asyncio.gather(
            call("scout_pitchers", _tasks(r)["scout_pitchers"]), call("scout_hitters", _tasks(r)["scout_hitters"]))
        stamp_probability(r["scout_pitchers"], ctx)
        r["pitching"], r["lineup"] = await asyncio.gather(
            call("pitching_coach", _tasks(r)["pitching_coach"]), call("bench_coach", _tasks(r)["bench_coach"]))

        while True:
            issues = check_plan(game_pk, team_id, ctx["opponent_id"], medical=r["medical"],
                                scout_pitchers=r["scout_pitchers"], scout_hitters=r["scout_hitters"],
                                pitching=r["pitching"], lineup=r["lineup"], ledger=deps.ledger)
            blocking = [i for i in issues if i.owner in FIXABLE]
            audit.log("checker", round=rounds, passed=not blocking, issues=[i.as_dict() for i in issues])
            out_list = [f"{s.name} ({s.player_id})" for s in r["medical"].statuses if s.status == "out"]
            review_task = (
                "Review the full plan and the checker results.\n"
                f"Players OUT per the Team Doctor (this is the complete list): {', '.join(out_list) or 'none'}\n"
                f"Checker issues (code-verified; every one must be fixed): {json.dumps([i.as_dict() for i in blocking])}\n"
                f"Team Doctor: {_j(r['medical'])}\nScout, opposing pitchers: {_j(r['scout_pitchers'])}\n"
                f"Scout, opposing hitters: {_j(r['scout_hitters'])}\nPitching plan: {_j(r['pitching'])}\n"
                f"Lineup plan: {_j(r['lineup'])}")
            r["review"] = await call("manager", review_task)
            audit.log("manager_review", round=rounds, approved=r["review"].approved,
                      fixes=[f.model_dump() for f in r["review"].fixes])
            if not blocking and r["review"].approved:
                status = "approved"
                break
            if rounds >= config.MAX_FIX_ROUNDS:
                status = "needs_human_review"
                break
            rounds += 1
            # Every checker issue goes to its owner, plus whatever the manager asked for.
            todo: dict[str, list[str]] = {}
            for i in blocking:
                todo.setdefault(i.owner, []).append(i.message)
            for f in r["review"].fixes:
                todo.setdefault(f.to, []).append(f"Manager: {f.instruction}")
            audit.log("fix_round", round=rounds, targets={k: v for k, v in todo.items()})
            names = [n for n in ("scout_pitchers", "scout_hitters", "pitching_coach", "bench_coach") if n in todo]
            results = await asyncio.gather(*(call(n, _fix_task(_tasks(r)[n], r[key[n]], todo[n])) for n in names))
            for n, out in zip(names, results):
                r[key[n]] = out
            stamp_probability(r["scout_pitchers"], ctx)

        comms_task = (f"Write the three briefings for this plan.\nManager review: {_j(r['review'])}\n"
                      f"Lineup plan: {_j(r['lineup'])}\nPitching plan: {_j(r['pitching'])}\n"
                      f"Scout, opposing pitchers: {_j(r['scout_pitchers'])}\nScout, opposing hitters: {_j(r['scout_hitters'])}\n"
                      f"Team Doctor: {_j(r['medical'])}")
        r["comms"] = await call("clubhouse_comms", comms_task)
        def comms_check(c: CommsPackage) -> list[Issue]:
            return (check_numbers("clubhouse_comms", c, ledger_numbers(deps.ledger))
                    + check_prompt_leak("clubhouse_comms", c) + check_briefing_leaks(c, r["medical"], r["pitching"]))

        comms_issues = comms_check(r["comms"])
        audiences = sorted(b.audience for b in r["comms"].briefings)
        if audiences != ["coaches", "hitters", "pitchers"]:
            comms_issues.append(Issue("clubhouse_comms", "briefings", f"Need one briefing per audience, got {audiences}."))
        if comms_issues:
            audit.log("checker", round="comms", passed=False, issues=[i.as_dict() for i in comms_issues])
            r["comms"] = await call("clubhouse_comms", _fix_task(comms_task, r["comms"], [i.message for i in comms_issues]))
            issues += comms_check(r["comms"])
    except (UsageLimitExceeded, AgentStepLimit) as exc:
        status = "stopped_by_budget"
        audit.log("budget_stop", reason=str(exc))

    plan = assemble(run_id, ctx, r, status, rounds, issues, tally, time.perf_counter() - started, notes)
    (audit.run_dir / "plan.json").write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
    # The tool results behind every number, so edits can be re-checked later without new model calls.
    (audit.run_dir / "ledger.json").write_text(json.dumps(deps.ledger, default=str), encoding="utf-8")
    audit.log("run_end", status=status, fix_rounds=rounds, seconds=plan["usage"]["seconds"], totals=plan["usage"]["total"],
              by_agent=plan["usage"]["by_agent"], run_requests=usage.requests, run_tool_calls=usage.tool_calls)
    return plan


def assemble(run_id: str, ctx: dict, r: dict, status: str, rounds: int, issues: list[Issue], tally: Tally,
             seconds: float, notes: str | None) -> dict:
    dump = lambda m: m.model_dump() if m else None  # noqa: E731
    briefs = {b.audience: b.model_dump() for b in r["comms"].briefings} if r["comms"] else {}
    sections = {
        "lineup_card": dump(r["lineup"]), "pitching_plan": dump(r["pitching"]),
        "opposing_pitchers_report": dump(r["scout_pitchers"]), "opposing_hitters_report": dump(r["scout_hitters"]),
        "medical_report": dump(r["medical"]), "manager_review": dump(r["review"]),
        "hitters_briefing": briefs.get("hitters"), "pitchers_briefing": briefs.get("pitchers"),
        "coaches_briefing": briefs.get("coaches"),
    }
    by_agent = {k: {**v, "seconds": round(v["seconds"], 1), "cost_usd": round(v["cost_usd"], 5)}
                for k, v in tally.by_agent.items()}
    return {
        "run_id": run_id, "status": status, "game": ctx, "manager_notes": notes,
        "sections": sections,
        "packets": {aud: [s for s in names if sections.get(s) is not None] for aud, names in PACKETS.items()},
        "checker": {"fix_rounds": rounds, "open_issues": [i.as_dict() for i in issues]},
        "usage": {"seconds": round(seconds, 1), "total": tally.total(), "by_agent": by_agent,
                  "pricing_source": config.PRICE_SOURCE},
    }
