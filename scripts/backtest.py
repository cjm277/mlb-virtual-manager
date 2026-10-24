"""Backtest: run the full staff on real September 2026 games and compare each plan to what actually happened.

For each game we manage one team, plan it using only data from before the game (as the app always does),
then compare against that team's real box score:
  - starting nine: how many of our 9 actually started, and at the same position
  - batting order: how many of the shared players batted in the same slot (and how far off the rest were)
  - starting pitcher: did our pick start? did our scout call the opponent's starter (or bulk pitcher)?
  - relievers: of the relievers the real manager used, how many were in our plan for the situation the
    game actually turned into (close / blowout / starter knocked out early)
Reference point: how many of a team's real starters also started its previous game.

Usage:
  python scripts/backtest.py --run        # build the plans (about $0.02 and 1 minute each, two at a time)
  python scripts/backtest.py              # compare saved plans to the box scores and write the report
Writes:
  evidence/logs/phase7_backtest/<run>/    plan.json, audit.jsonl, ledger.json for each game
  evidence/tests/phase7_backtest.md       the table, plus evidence/tests/phase7_interpretation.md appended
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import config, db  # noqa: E402
from backend.engine.rotation import turn_taker  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SAVE = ROOT / "evidence" / "logs" / "phase7_backtest"
REPORT = ROOT / "evidence" / "tests" / "phase7_backtest.md"
WINDOW = ("2026-09-08", "2026-09-20")
PREFERRED = [141, 119, 147, 117, 144, 136, 143, 112, 135, 121, 158, 140, 111, 110, 114, 116]   # managed-team order


def pick_games(n: int = 8) -> list[dict]:
    """n September games with 2n different teams; we manage the first team of each pair from PREFERRED."""
    games = db.rows("SELECT game_pk, game_date, home_team_id, away_team_id, home_score, away_score FROM games "
                    "WHERE game_date BETWEEN ? AND ? ORDER BY game_date, game_pk", *WINDOW)
    used, chosen = set(), []
    dates = sorted({g["game_date"] for g in games})
    for team in PREFERRED:
        if len(chosen) == n or team in used:
            continue
        start = dates[min(len(chosen) * 1, len(dates) - 1)]      # spread the picks across the window
        for g in [g for g in games if g["game_date"] >= start]:
            opp = g["away_team_id"] if g["home_team_id"] == team else g["home_team_id"] if g["away_team_id"] == team else None
            if opp and opp not in used:
                chosen.append({**dict(g), "team_id": team, "opponent_id": opp})
                used |= {team, opp}
                break
    return chosen


async def run_all(games: list[dict]) -> None:
    from backend.agents.team import build_game_plan

    sem = asyncio.Semaphore(2)

    async def one(g: dict) -> None:
        async with sem:
            plan = await build_game_plan(g["game_pk"], g["team_id"])
            src = config.RUNS_DIR / plan["run_id"]
            dst = SAVE / plan["run_id"]
            dst.mkdir(parents=True, exist_ok=True)
            for f in ("plan.json", "audit.jsonl", "ledger.json"):
                shutil.copy(src / f, dst / f)
            print(f"  {g['game_date']} team {g['team_id']}: {plan['status']} in {plan['usage']['seconds']}s, "
                  f"${plan['usage']['total']['cost_usd']:.4f}", flush=True)

    await asyncio.gather(*(one(g) for g in games))


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def actual_lineup(game_pk: int, team_id: int) -> dict[int, tuple[int, str]]:
    return {r["player_id"]: (r["lineup_slot"], r["start_position"]) for r in db.rows(
        "SELECT player_id, lineup_slot, start_position FROM batting_lines WHERE game_pk = ? AND team_id = ? "
        "AND is_starter = 1", game_pk, team_id)}


def previous_lineup(team_id: int, game_date: str) -> dict[int, tuple[int, str]]:
    prev = db.one("""SELECT game_pk FROM batting_lines WHERE team_id = ? AND game_date < ? AND is_starter = 1
                     ORDER BY game_date DESC LIMIT 1""", team_id, game_date)
    return actual_lineup(prev["game_pk"], team_id) if prev else {}


def actual_pitchers(game_pk: int, team_id: int) -> tuple[int, int, list[int]]:
    rows = db.rows("SELECT player_id, is_starter, outs FROM pitching_lines WHERE game_pk = ? AND team_id = ? "
                   "ORDER BY appearance_order", game_pk, team_id)
    starter = next(r for r in rows if r["is_starter"])
    return starter["player_id"], starter["outs"], [r["player_id"] for r in rows if not r["is_starter"]]


def situation(g: dict, team_id: int, starter_outs: int) -> str:
    ours = g["home_score"] if g["home_team_id"] == team_id else g["away_score"]
    theirs = g["away_score"] if g["home_team_id"] == team_id else g["home_score"]
    if starter_outs < 12:
        return "starter_early_exit"
    if abs(ours - theirs) >= 5:
        return "blowout_lead" if ours > theirs else "blowout_deficit"
    return "close_late_lead" if ours > theirs else "close_late_tied_or_trailing"


def compare(run_dir: Path) -> dict:
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    gc = plan["game"]
    team, opp, pk = gc["team_id"], gc["opponent_id"], gc["game_pk"]
    g = dict(db.one("SELECT * FROM games WHERE game_pk = ?", pk))
    s = plan["sections"]
    ours = {x["player_id"]: (x["slot"], x["position"]) for x in s["lineup_card"]["lineup"]}
    real = actual_lineup(pk, team)
    common = set(ours) & set(real)
    same_slot = sum(ours[p][0] == real[p][0] for p in common)
    slot_gap = sum(abs(ours[p][0] - real[p][0]) for p in common) / len(common) if common else None
    same_pos = sum(ours[p][1] == real[p][1] for p in common)
    prev = previous_lineup(team, gc["game_date"])
    prev_common = set(prev) & set(real)
    prev_same_slot = sum(prev[p][0] == real[p][0] for p in prev_common)

    real_sp, sp_outs, relievers = actual_pitchers(pk, team)
    our_sp = s["pitching_plan"]["starter"]["player_id"]
    opp_real_sp, _, _ = actual_pitchers(pk, opp)
    opp_pick = s["opposing_pitchers_report"]["opposing_starter"]
    opp_called = opp_pick["player_id"] in {opp_real_sp, turn_taker(pk, opp)}

    sit = situation(g, team, sp_outs)
    plan_for_sit = next((sc["pitcher_ids"] for sc in s["pitching_plan"]["scenarios"] if sc["scenario"] == sit), [])
    roles = {b["player_id"]: b["role"] for b in s["pitching_plan"]["bullpen"]}
    in_plan = sum(r in plan_for_sit for r in relievers)
    marked_unavailable = [r for r in relievers if roles.get(r) == "unavailable"]
    names = {r["player_id"]: r["full_name"] for r in db.rows("SELECT player_id, full_name FROM players")}
    abbrev = {r["team_id"]: r["abbrev"] for r in db.rows("SELECT team_id, abbrev FROM teams")}
    score = (f"{g['home_score']}-{g['away_score']}" if g["home_team_id"] == team else f"{g['away_score']}-{g['home_score']}")
    won = (g["home_score"] > g["away_score"]) == (g["home_team_id"] == team)
    return {
        "run": run_dir.name, "date": gc["game_date"], "team": abbrev[team], "opp": abbrev[opp],
        "result": f"{'W' if won else 'L'} {score}", "status": plan["status"], "fix_rounds": plan["checker"]["fix_rounds"],
        "nine": len(common), "prev_nine": len(prev_common), "same_pos": same_pos, "same_slot": same_slot,
        "prev_same_slot": prev_same_slot,
        "slot_gap": slot_gap,
        "our_sp": names.get(our_sp), "real_sp": names.get(real_sp), "sp_match": our_sp == real_sp,
        "our_sp_was_on_turn": None,
        "opp_pick": opp_pick["name"], "opp_real": names.get(opp_real_sp), "opp_called": opp_called,
        "opp_pct": opp_pick.get("probability_pct"),
        "situation": sit, "relievers_used": len(relievers), "relievers_in_plan": in_plan,
        "used_but_we_marked_unavailable": [names.get(r) for r in marked_unavailable],
        "left_out": [names.get(p) for p in real if p not in ours], "we_added": [names.get(p) for p in ours if p not in real],
        "cost": plan["usage"]["total"]["cost_usd"], "seconds": plan["usage"]["seconds"],
        "tokens_in": plan["usage"]["total"]["input_tokens"], "tokens_cached": plan["usage"]["total"]["cached_tokens"],
        "tokens_out": plan["usage"]["total"]["output_tokens"],
    }


def report(rows: list[dict]) -> str:
    n = len(rows)
    avg = lambda k: sum(r[k] for r in rows) / n  # noqa: E731
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"  # noqa: E731
    rel_used = sum(r["relievers_used"] for r in rows)
    rel_in = sum(r["relievers_in_plan"] for r in rows)
    lines = [
        "# Phase 7 backtest: the staff's plan vs. what real managers did",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} by `scripts/backtest.py`. {n} September 2026 games, {2 * n} different teams. "
        "Each plan was built exactly as the app builds it, using only data from before the game. It was then "
        "compared with that team's real box score. Full plans and audit trails are in `evidence/logs/phase7_backtest/`.",
        "",
        "## Results",
        "",
        "| Date | We managed | Result | Starting nine (of 9) | Same position | Same batting slot (prev. game) | Our starter = real starter? | Scout called their starter? | Situation | Relievers used that were in our plan for it |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['date']} | {r['team']} vs {r['opp']} | {r['result']} | {r['nine']} (prev. game: {r['prev_nine']}) | "
            f"{r['same_pos']} of {r['nine']} | {r['same_slot']} of {r['nine']} ({r['prev_same_slot']} of {r['prev_nine']}) | "
            f"{'yes' if r['sp_match'] else 'no'}: {r['our_sp']}{'' if r['sp_match'] else ' (real: ' + str(r['real_sp']) + ')'} | "
            f"{'yes' if r['opp_called'] else 'no'}: {r['opp_pick']}{'' if r['opp_called'] else ' (real: ' + str(r['opp_real']) + ')'}"
            f"{' (' + str(r['opp_pct']) + '%)' if r['opp_pct'] is not None else ''} | {r['situation'].replace('_', ' ')} | "
            f"{r['relievers_in_plan']} of {r['relievers_used']} |")
    lines += [
        f"| **Total / average** | | | **{avg('nine'):.1f}** (prev. game: {avg('prev_nine'):.1f}) | "
        f"{pct(sum(r['same_pos'] for r in rows), sum(r['nine'] for r in rows))} | "
        f"{pct(sum(r['same_slot'] for r in rows), sum(r['nine'] for r in rows))} "
        f"(prev. game: {pct(sum(r['prev_same_slot'] for r in rows), sum(r['prev_nine'] for r in rows))}); "
        f"avg. {sum(r['slot_gap'] or 0 for r in rows) / n:.1f} slots off | "
        f"{sum(r['sp_match'] for r in rows)} of {n} | {sum(r['opp_called'] for r in rows)} of {n} | | "
        f"{rel_in} of {rel_used} ({pct(rel_in, rel_used)}) |",
        "",
        "## Who differed",
        "",
        "| Game | Real starters we benched | Players we started instead | Relievers used that we had marked unavailable |",
        "|---|---|---|---|",
        *[f"| {r['date']} {r['team']} | {', '.join(filter(None, r['left_out'])) or '-'} | {', '.join(filter(None, r['we_added'])) or '-'} | "
          f"{', '.join(filter(None, r['used_but_we_marked_unavailable'])) or 'none'} |" for r in rows],
        "",
        "## Cost of the backtest runs",
        "",
        f"{n} plans: average **${avg('cost'):.4f}** and **{avg('seconds'):.0f} s** per plan; "
        f"{avg('tokens_in'):,.0f} input tokens ({pct(sum(r['tokens_cached'] for r in rows), sum(r['tokens_in'] for r in rows))} cached) "
        f"and {avg('tokens_out'):,.0f} output tokens on average. "
        f"Statuses: {', '.join(sorted({r['status'] for r in rows}))}; fix rounds: {sum(r['fix_rounds'] for r in rows)} in total.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="build the plans first (costs money)")
    args = ap.parse_args()
    if args.run:
        games = pick_games()
        print(f"Building {len(games)} plans...")
        asyncio.run(run_all(games))
    rows = [compare(d) for d in sorted(SAVE.iterdir()) if (d / "plan.json").exists()]
    rows.sort(key=lambda r: r["date"])
    (SAVE / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    text = report(rows)
    notes = REPORT.parent / "phase7_interpretation.md"      # hand-written; kept across regenerations
    if notes.exists():
        text += "\n" + notes.read_text(encoding="utf-8")
    REPORT.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
