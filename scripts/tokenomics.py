"""Phase 8 tokenomics: what a game plan really costs, what that means at scale, and two cost cutters tested
before-and-after on the same backtest games.

Usage:
  python scripts/tokenomics.py --run A_baseline --reps 2     # build plans under one condition (costs money)
  python scripts/tokenomics.py                               # analyze saved runs and write the report

Conditions (each switches the Phase 8 cost cutters through env vars; see backend/config.py):
  A_baseline              both off: the app as it was at the end of Phase 7
  B_self_check            agents run the code checker on their own output before handing it in (fewer hops)
  C_self_check_compact    B, plus compact matchups output (shorter tool outputs)
Every experiment run asks Portkey for a fresh answer, so a repeat of the same game is a real, paid run.

Reads:
  runs/                                   the real plans built so far (production usage before Phase 8)
  evidence/logs/phase8_tokenomics/<condition>/<run>/   the experiment runs
Writes:
  evidence/tests/phase8_tokenomics.md     cost table, scale-up, users question, before/after comparison
  evidence/logs/phase8_tokenomics/results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

SAVE = ROOT / "evidence" / "logs" / "phase8_tokenomics"
REPORT = ROOT / "evidence" / "tests" / "phase8_tokenomics.md"
NOTES = ROOT / "evidence" / "tests" / "phase8_interpretation.md"      # hand-written; appended to the report
CONDITIONS = {
    "A_baseline": {"MVM_SELF_CHECK_RETRIES": "0", "MVM_COMPACT_MATCHUPS": "0"},
    "B_self_check": {"MVM_SELF_CHECK_RETRIES": "1", "MVM_COMPACT_MATCHUPS": "0"},
    "C_self_check_compact": {"MVM_SELF_CHECK_RETRIES": "1", "MVM_COMPACT_MATCHUPS": "1"},
}
SHIPPED = "B_self_check"      # the measured-best condition, and the app's default settings since Phase 8
LABEL = {"A_baseline": "A. Before (Phase 7 app)", "B_self_check": "B. + Self-check (fewer hops)",
         "C_self_check_compact": "C. + Self-check + compact matchups"}

# Scale-up assumptions (stated in the report)
GAMES_PER_MONTH = 26
GAMES_PER_SEASON = 162
MLB_TEAMS = 30
CHAT_EDITS_PER_GAME = 3
# The price on the course's lecture slide (for gpt-5.6-luna): $0.20 in / $1.20 out, no cached rate given.
SLIDE_PRICE = (0.20, 0.20, 1.20)


# ---------------------------------------------------------------------------
# Running the experiment
# ---------------------------------------------------------------------------

def run(condition: str, reps: int, concurrency: int, n_games: int = 8) -> None:
    os.environ.update(CONDITIONS[condition])
    os.environ["MVM_GATEWAY_FORCE_REFRESH"] = "1"
    from backend import config
    from backend.agents.team import build_game_plan
    from backtest import pick_games

    config.RUNS_DIR = SAVE / condition
    games = pick_games()[:n_games]
    sem = asyncio.Semaphore(concurrency)

    async def one(g: dict, rep: int) -> None:
        run_id = f"{g['game_date']}_t{g['team_id']}_{condition}_r{rep}"
        if (config.RUNS_DIR / run_id / "plan.json").exists():
            return
        async with sem:
            plan = await build_game_plan(g["game_pk"], g["team_id"], run_id=run_id)
            print(f"  {run_id}: {plan['status']} in {plan['usage']['seconds']}s, "
                  f"${plan['usage']['total']['cost_usd']:.4f}, fix rounds {plan['checker']['fix_rounds']}", flush=True)

    async def main() -> None:
        await asyncio.gather(*(one(g, rep) for rep in range(1, reps + 1) for g in games))

    print(f"{condition}: {len(games)} games x {reps} reps, {concurrency} at a time")
    asyncio.run(main())


# ---------------------------------------------------------------------------
# Measuring one run
# ---------------------------------------------------------------------------

def events(run_dir: Path) -> list[dict]:
    out = []
    for line in (run_dir / "audit.jsonl").open(encoding="utf-8"):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:      # one record torn by a concurrent write (fixed in backend/audit.py)
            pass
    return out


def list_price(inp: int, cached: int, out: int, price=(0.20, 0.02, 0.50)) -> float:
    return ((inp - cached) * price[0] + cached * price[1] + out * price[2]) / 1e6


def measure(run_dir: Path, with_backtest: bool = False) -> dict:
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    ev = events(run_dir)
    t = plan["usage"]["total"]
    checks = [e for e in ev if e["event"] == "checker" and e["round"] != "comms"]
    first = checks[0]["issues"] if checks else []
    m = {
        "run": run_dir.name, "game": f"{plan['game']['game_date']} {plan['game']['team']}",
        "status": plan["status"], "fix_rounds": plan["checker"]["fix_rounds"],
        "open_issues": len(plan["checker"]["open_issues"]),
        "first_check_issues": len([i for i in first if i["owner"] != "team_doctor"]),
        "unsupported_numbers": sum(i["code"] == "unsupported_number" for e in checks for i in e["issues"]),
        "self_checks": sum(e["event"] == "self_check" for e in ev),
        "manager_calls": plan["usage"]["by_agent"].get("manager", {}).get("calls", 0),
        "agent_calls": sum(a.get("calls", 0) for a in plan["usage"]["by_agent"].values()),
        "model_steps": t["model_steps"], "gateway_hits": t.get("gateway_cache_hits", 0),
        "input": t["input_tokens"], "cached": t["cached_tokens"], "output": t["output_tokens"],
        # Billed-equivalent cost: what the tokens cost at list price even if Portkey answered from its cache.
        "cost": list_price(t["input_tokens"], t["cached_tokens"], t["output_tokens"]),
        "cost_slide": list_price(t["input_tokens"], 0, t["output_tokens"], SLIDE_PRICE),
        "seconds": plan["usage"]["seconds"],
        "tool_chars": sum(e.get("result_chars", 0) for e in ev if e["event"] == "tool_result"),
        "matchup_chars": sum(e.get("result_chars", 0) for e in ev if e["event"] == "tool_result" and e["tool"] == "matchups"),
        "hitter_plans": len((plan["sections"].get("opposing_pitchers_report") or {}).get("hitter_plans", [])),
        "by_agent": plan["usage"]["by_agent"],
    }
    if with_backtest:
        from backtest import compare
        b = compare(run_dir)
        m.update({k: b[k] for k in ("nine", "same_pos", "sp_match", "opp_called", "relievers_used", "relievers_in_plan")})
    return m


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 1 else f"${x:.4f}" if x < 0.1 else f"${x:.3f}"


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    mean = lambda k: sum(r[k] for r in rows) / n  # noqa: E731
    costs = sorted(r["cost"] for r in rows)
    return {"n": n, "cost": mean("cost"), "median": st.median(costs), "p90": costs[min(n - 1, int(0.9 * n))],
            "max": costs[-1], "min": costs[0], "cost_slide": mean("cost_slide"), "input": mean("input"),
            "cached_share": sum(r["cached"] for r in rows) / sum(r["input"] for r in rows), "output": mean("output"),
            "seconds": mean("seconds"), "model_steps": mean("model_steps"), "fix_rounds": mean("fix_rounds"),
            "any_fix": sum(r["fix_rounds"] > 0 for r in rows) / n, "manager_calls": mean("manager_calls"),
            "agent_calls": mean("agent_calls"), "approved": sum(r["status"] == "approved" for r in rows) / n,
            "open_issues": mean("open_issues"), "first_check_issues": mean("first_check_issues"),
            "unsupported_numbers": mean("unsupported_numbers"), "self_checks": mean("self_checks"),
            "tool_chars": mean("tool_chars"), "matchup_chars": mean("matchup_chars"), "hitter_plans": mean("hitter_plans")}


def production_rows() -> tuple[list[dict], list[dict], dict]:
    runs = [measure(d) for d in sorted((ROOT / "runs").iterdir()) if (d / "plan.json").exists()]
    fresh = [r for r in runs if r["gateway_hits"] == 0]
    reruns = [r for r in runs if r["gateway_hits"] > 0]
    chat_cost = chat_msgs = 0
    for d in (ROOT / "runs").iterdir():
        if (d / "chat.json").exists():
            usage = json.loads((d / "plan.json").read_text(encoding="utf-8"))["usage"].get("chat") or {}
            chat_cost += usage.get("cost_usd", 0)
            chat_msgs += sum(m["role"] == "manager" for m in json.loads((d / "chat.json").read_text(encoding="utf-8")))
    return fresh, reruns, {"messages": chat_msgs, "cost": chat_cost, "per_message": chat_cost / chat_msgs if chat_msgs else 0}


def agent_shares(rows: list[dict]) -> list[tuple[str, float, float]]:
    tot = defaultdict(float)
    for r in rows:
        for a, v in r["by_agent"].items():
            tot[a] += list_price(v["input_tokens"], v["cached_tokens"], v["output_tokens"])
    whole = sum(tot.values())
    return [(a, c / len(rows), c / whole) for a, c in sorted(tot.items(), key=lambda x: -x[1])]


def scale_table(per_plan: float, per_chat: float) -> list[str]:
    game = per_plan + CHAT_EDITS_PER_GAME * per_chat
    rows = [("One game plan", per_plan, game),
            (f"One team, one month ({GAMES_PER_MONTH} games)", per_plan * GAMES_PER_MONTH, game * GAMES_PER_MONTH),
            (f"One team, full season ({GAMES_PER_SEASON} games)", per_plan * GAMES_PER_SEASON, game * GAMES_PER_SEASON),
            (f"All {MLB_TEAMS} MLB teams, one month", per_plan * GAMES_PER_MONTH * MLB_TEAMS, game * GAMES_PER_MONTH * MLB_TEAMS),
            (f"All {MLB_TEAMS} MLB teams, full season ({GAMES_PER_SEASON * MLB_TEAMS:,} team-games)",
             per_plan * GAMES_PER_SEASON * MLB_TEAMS, game * GAMES_PER_SEASON * MLB_TEAMS)]
    out = ["| Scope | Plan only | Plan + 3 chat edits |", "|---|---|---|"]
    out += [f"| {name} | {money(a)} | {money(b)} |" for name, a, b in rows]
    return out


USER_GROUPS = [
    # (who, users, games per season, plans per game, chat edits per game)
    ("100 users: every MLB staff plus 70 Triple-A / Double-A clubs", 100, 150, 1.2, 3),
    ("10,000 users: affiliated minors (120), NCAA D1-D3 (~1,000), NAIA/JUCO (~700), high-school varsity (~8,200)",
     10_000, 40, 1.2, 3),
    ("10,000 users as individual coaches (about 10 per MLB/MiLB staff on 1,000 staffs) who share one plan per game",
     10_000, None, None, None),
]


def users_table(per_plan: float, per_chat: float, tokens_per_plan: float) -> list[str]:
    out = ["| Who the users are | Plans per season | Model cost per season | Per user per season | Busiest hour (7 PM starts) |",
           "|---|---|---|---|---|"]
    for who, users, games, plans, chats in USER_GROUPS[:2]:
        n_plans = users * games * plans
        cost = n_plans * per_plan + users * games * chats * per_chat
        # About half of all users play on a given night and build within the 2 hours before first pitch.
        peak = users * 0.5 * plans / 2
        out.append(f"| {who} | {n_plans:,.0f} | {money(cost)} | {money(cost / users)} | "
                   f"~{peak:,.0f} plans/hour = {peak * 20 / 60:,.0f} model calls and "
                   f"{peak * tokens_per_plan / 60 / 1e6:,.2f}M tokens per minute |")
    who, users = USER_GROUPS[2][:2]
    staffs, games = 1_000, 140
    cost = staffs * games * 1.2 * per_plan + users * games * 2 * per_chat
    peak = staffs * 0.5 * 1.2 / 2
    out.append(f"| {who} | {staffs * games * 1.2:,.0f} | {money(cost)} | {money(cost / users)} | "
               f"~{peak:,.0f} plans/hour = {peak * tokens_per_plan / 60 / 1e6:,.2f}M tokens per minute, plus chat |")
    return out


def report() -> str:
    fresh, reruns, chat = production_rows()
    prod = summary(fresh)
    exp = {c: [measure(d, with_backtest=True) for d in sorted((SAVE / c).iterdir()) if (d / "plan.json").exists()]
           for c in CONDITIONS if (SAVE / c).exists()}
    exp = {c: rows for c, rows in exp.items() if rows}
    sums = {c: summary(rows) for c, rows in exp.items()}
    SAVE.mkdir(parents=True, exist_ok=True)
    (SAVE / "results.json").write_text(json.dumps({c: [{k: v for k, v in r.items() if k != "by_agent"} for r in rows]
                                                   for c, rows in exp.items()}, indent=2), encoding="utf-8")
    shipped = SHIPPED if SHIPPED in sums else None
    per_plan = sums[shipped]["cost"] if shipped else prod["cost"]
    pc = chat["per_message"]

    L = [
        "# Phase 8 tokenomics: what a game plan costs, at every scale",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `scripts/tokenomics.py` from real token counts in the audit "
        "trail of every run (input, cached input and output tokens are logged for each model call).",
        "",
        "**Pricing.** gpt-6-luna list price: **$0.20 per 1M input tokens, $0.02 per 1M cached input tokens, $0.50 per 1M "
        "output tokens** (genai-prices \"GPT-6 Luna\", checked against OpenAI's pricing page on 2026-10-12). The course's "
        "lecture slide prices a different model (gpt-5.6-luna) at $0.20 in / $1.20 out with no cached rate; that is shown "
        "as a worst-case sensitivity line. Model cost only: hosting and data are discussed separately.",
        "",
        "## 1. Real token counts",
        "",
        f"**{prod['n']} real game plans** built through the app and the command line between Phases 4 and 7 (`runs/`), "
        f"plus the {sum(len(v) for v in exp.values())} Phase 8 experiment runs below. Fresh builds only: "
        f"{len(reruns)} rerun(s) that Portkey answered partly or wholly from its cache are counted separately.",
        "",
        "| Per game plan | Mean | Median | 90th pct. | Cheapest | Most expensive |",
        "|---|---|---|---|---|---|",
        f"| Cost (list price) | **{money(prod['cost'])}** | {money(prod['median'])} | {money(prod['p90'])} | "
        f"{money(prod['min'])} | {money(prod['max'])} |",
        "",
        f"Average plan: **{prod['input']:,.0f} input tokens ({prod['cached_share']:.0%} cached), {prod['output']:,.0f} output "
        f"tokens, {prod['model_steps']:.0f} model calls, {prod['seconds']:.0f} s.** Input is about "
        f"{list_price(prod['input'], prod['input'] * prod['cached_share'], 0) / prod['cost']:.0%} of the bill even though "
        "output costs 2.5x more per token: each agent re-reads its instructions and every tool result on each step of its "
        f"loop. A chat edit costs **{money(pc)}** per message ({chat['messages']} real messages). "
        f"Lecture-slide pricing would make the average plan {money(prod['cost_slide'])}.",
        "",
        "Where the money goes (fresh production runs):",
        "",
        "| Agent | Cost per plan | Share |",
        "|---|---|---|",
        *[f"| {a.replace('_', ' ')} | {money(c)} | {s:.0%} |" for a, c, s in agent_shares(fresh)],
        "",
        f"Fix rounds are the biggest swing factor: {prod['any_fix']:.0%} of plans needed at least one, and those plans cost "
        f"{money(summary([r for r in fresh if r['fix_rounds']]) ['cost'])} on average vs "
        f"{money(summary([r for r in fresh if not r['fix_rounds']])['cost'])} for plans approved on the first pass.",
        "",
        "## 2. Cost at scale",
        "",
        f"Using the shipped configuration's measured average of **{money(per_plan)} per plan** "
        f"({'condition B below, the settings the app now ships with' if shipped else 'production runs'}) and {money(pc)} per chat edit. "
        f"\"Plan + 3 chat edits\" assumes the manager makes three chat changes per game.",
        "",
        *scale_table(per_plan, pc),
        "",
        f"At the slide's worst-case pricing, the full 30-team season would be "
        f"{money(sums[shipped]['cost_slide'] * GAMES_PER_SEASON * MLB_TEAMS if shipped else prod['cost_slide'] * 4860)} "
        "for plans only. For comparison, Yale gives each student $40 of tokens.",
        "",
        "## 3. The 100 and 10,000 users question",
        "",
        "A \"user\" here is one coaching staff that builds a plan before each of its games (1.2 plans per game, allowing for "
        "a rebuild when the lineup or starter changes) and makes 3 chat edits. Season lengths: Triple-A/Double-A about "
        "150 games, college and high school about 40 on average.",
        "",
        *users_table(per_plan, pc, (sums[shipped] if shipped else prod)['input'] + (sums[shipped] if shipped else prod)['output']),
        "",
    ]
    if exp:
        L += [
            "## 4. Cost-cutting experiments, before and after",
            "",
            "Same 8 September 2026 backtest games (16 teams) for every condition, each game run twice, all three conditions "
            "run side by side at the same time against the same API. Portkey's cache was bypassed so every run was a real, "
            "billed run. Quality is measured by the code checker (did the plan pass first time, was anything left open, any "
            "made-up numbers) and the Manager (fix rounds). Agreement with what real managers did is shown only as a "
            "reference that a cost cut did not change the staff's thinking: matching real managers is not the goal, since "
            "the app is meant to offer evidence-based alternatives to traditional thinking.",
            "",
            "| | " + " | ".join(LABEL[c] for c in sums) + " |",
            "|---|" + "---|" * len(sums),
        ]

        def row(label: str, fn) -> str:
            return f"| {label} | " + " | ".join(fn(c, s) for c, s in sums.items()) + " |"

        bt = lambda c, k: sum(r[k] for r in exp[c])  # noqa: E731
        base = sums.get("A_baseline")
        delta = lambda s, k: (f" ({(s[k] / base[k] - 1):+.0%})" if base and s is not base and base[k] else "")  # noqa: E731
        L += [
            row("Runs", lambda c, s: f"{s['n']}"),
            "| **Cost** | " + " | ".join("" for _ in sums) + " |",
            row("Cost per plan (mean)", lambda c, s: f"**{money(s['cost'])}**{delta(s, 'cost')}"),
            row("Cost per plan (median / 90th pct.)", lambda c, s: f"{money(s['median'])} / {money(s['p90'])}"),
            row("Input tokens (cached share)", lambda c, s: f"{s['input']:,.0f}{delta(s, 'input')} ({s['cached_share']:.0%})"),
            row("Output tokens", lambda c, s: f"{s['output']:,.0f}{delta(s, 'output')}"),
            row("Tool output characters (matchups)", lambda c, s: f"{s['tool_chars']:,.0f} ({s['matchup_chars']:,.0f})"),
            row("Model calls", lambda c, s: f"{s['model_steps']:.1f}"),
            row("Agent hops (agent runs per plan)", lambda c, s: f"{s['agent_calls']:.1f}"),
            row("Time per plan", lambda c, s: f"{s['seconds']:.0f} s{delta(s, 'seconds')}"),
            "| **Quality: process** | " + " | ".join("" for _ in sums) + " |",
            row("Approved by the Manager", lambda c, s: f"{s['approved']:.0%}"),
            row("Plans needing a fix round", lambda c, s: f"{s['any_fix']:.0%}"),
            row("Fix rounds per plan", lambda c, s: f"{s['fix_rounds']:.2f}"),
            row("Checker issues at first full check", lambda c, s: f"{s['first_check_issues']:.2f}"),
            row("Self-check catches (fixed inside the agent)", lambda c, s: f"{s['self_checks']:.2f}"),
            row("Open issues at the end", lambda c, s: f"{s['open_issues']:.2f}"),
            row("Made-up-number flags", lambda c, s: f"{s['unsupported_numbers']:.2f}"),
            row("Hitter plans written", lambda c, s: f"{s['hitter_plans']:.1f}"),
            "| **Agreement with real managers (reference only, not a target)** | " + " | ".join("" for _ in sums) + " |",
            row("Starting nine that really started", lambda c, s: f"{bt(c, 'nine') / s['n']:.1f} of 9"),
            row("...at the same position", lambda c, s: f"{bt(c, 'same_pos') / max(bt(c, 'nine'), 1):.0%}"),
            row("Our starter = real starter", lambda c, s: f"{bt(c, 'sp_match')} of {s['n']}"),
            row("Scout called their starter", lambda c, s: f"{bt(c, 'opp_called')} of {s['n']}"),
            row("Relievers used that were in our plan", lambda c, s: f"{bt(c, 'relievers_in_plan') / max(bt(c, 'relievers_used'), 1):.0%}"),
            "",
            "Per-run detail is in `evidence/logs/phase8_tokenomics/results.json`; every run's plan and audit trail is "
            "saved beside it.",
            "",
        ]
    return "\n".join(L)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", choices=list(CONDITIONS), help="build plans under this condition first (costs money)")
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--games", type=int, default=8, help="only the first N backtest games (smoke test)")
    args = ap.parse_args()
    if args.run:
        run(args.run, args.reps, args.concurrency, args.games)
        return
    text = report()
    if NOTES.exists():
        text += "\n" + NOTES.read_text(encoding="utf-8")
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
