"""Build a game plan from the command line.

Examples:
  python run_plan.py --team TOR --opp BOS --date 2026-09-15
  python run_plan.py --team TOR --opp BOS --date 2027-05-03 --notes "Give Kirk the day off."
  python run_plan.py --team TOR --opp BOS --list          # show every game between the two teams

Writes runs/<run_id>/plan.json (the plan) and runs/<run_id>/audit.jsonl (every agent step, tool call,
token count, timing and cost).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from backend.engine.games import games_between, teams

STAGE = {"team_doctor": "Team Doctor", "scout_pitchers": "Scout (pitchers)", "scout_hitters": "Scout (hitters)",
         "pitching_coach": "Pitching Coach", "bench_coach": "Bench Coach", "manager": "Manager",
         "clubhouse_comms": "Clubhouse Comms"}


def find_team(code: str) -> dict:
    code = code.strip().lower()
    for t in teams():
        if code in (t["abbrev"].lower(), str(t["team_id"]), t["team_name"].lower(), t["name"].lower()):
            return t
    raise SystemExit(f"Unknown team '{code}'. Use an abbreviation like TOR, BOS, NYY.")


def show(e: dict) -> None:
    ev, t = e["event"], f"[{e['t_plus_s']:6.1f}s]"
    if ev == "agent_start":
        print(f"{t} > {STAGE.get(e['agent'], e['agent'])} started")
    elif ev == "tool_result":
        print(f"{t}     {e['agent']}: {e['tool']}({', '.join(f'{k}={v}' for k, v in e['args'].items())})")
    elif ev == "tool_error":
        print(f"{t}     {e['agent']}: {e['tool']} refused: {e['error']}")
    elif ev == "agent_end":
        print(f"{t} < {STAGE.get(e['agent'], e['agent'])} done in {e['seconds']}s ({e['steps']} steps)")
    elif ev == "checker":
        verdict = "PASS" if e["passed"] else f"{len(e['issues'])} issue(s)"
        print(f"{t} * Consistency checker (round {e['round']}): {verdict}")
        for i in e["issues"]:
            print(f"           - [{i['owner']}] {i['message'][:150]}")
    elif ev == "manager_review":
        print(f"{t} * Manager: {'APPROVED' if e['approved'] else 'sent fixes'}")
    elif ev == "fix_round":
        print(f"{t} * Fix round {e['round']}: {', '.join(e['targets'])}")
    elif ev == "budget_stop":
        print(f"{t} ! Stopped by budget cap: {e['reason']}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="MLB Virtual Manager: build a game plan with the agent staff.")
    ap.add_argument("--team", required=True, help="Team you manage (e.g. TOR)")
    ap.add_argument("--opp", required=True, help="Opponent (e.g. BOS)")
    ap.add_argument("--date", help="Game date, YYYY-MM-DD (2026 or 2027 regular season)")
    ap.add_argument("--game", type=int, default=1, help="Game number on a doubleheader day (default 1)")
    ap.add_argument("--notes", help="Optional notes from the manager (treated as information, never as rules)")
    ap.add_argument("--list", action="store_true", help="List the games between the two teams and exit")
    args = ap.parse_args()

    us, them = find_team(args.team), find_team(args.opp)
    games = games_between(us["team_id"], them["team_id"])
    if args.list or not args.date:
        for g in games:
            print(f"{g['game_date']}  game {g['game_number']}  {g['home_away']:4s}  {g['venue']}  ({g['season']})")
        return
    match = [g for g in games if g["game_date"] == args.date and g["game_number"] == args.game]
    if not match:
        raise SystemExit(f"{us['abbrev']} and {them['abbrev']} don't play on {args.date} (game {args.game}). "
                         "Use --list to see their games.")

    from backend.agents.team import build_game_plan  # imported late so --list works without an API key
    print(f"Building the game plan: {us['name']} vs {them['name']}, {args.date} ({match[0]['home_away']})\n")
    plan = asyncio.run(build_game_plan(match[0]["game_pk"], us["team_id"], notes=args.notes, on_event=show))

    s = plan["sections"]
    print(f"\nStatus: {plan['status'].upper()}  (fix rounds: {plan['checker']['fix_rounds']})")
    if s["pitching_plan"]:
        st = s["pitching_plan"]["starter"]
        print(f"Starter: {st['name']} ({st['throws']}HP), about {st['expected_innings']} IP / {st['pitch_count_limit']} pitches")
    if s["lineup_card"]:
        print(f"Facing: {s['lineup_card']['opposing_starter_assumed']['name']}")
        for spot in sorted(s["lineup_card"]["lineup"], key=lambda x: x["slot"]):
            print(f"  {spot['slot']}. {spot['name']:24s} {spot['position']:3s} ({spot['bats']})")
    for i in plan["checker"]["open_issues"]:
        print(f"  open issue [{i['owner']}]: {i['message'][:150]}")
    u = plan["usage"]
    print(f"\nTokens: {u['total']['input_tokens']:,} input ({u['total']['cached_tokens']:,} cached), "
          f"{u['total']['output_tokens']:,} output over {u['total']['model_steps']} model calls "
          f"({u['total']['gateway_cache_hits']} answered from Portkey's cache)")
    print(f"Cost: ${u['total']['cost_usd']:.4f} at list price  |  Time: {u['seconds']}s")
    print(f"Plan:  runs/{plan['run_id']}/plan.json\nAudit: runs/{plan['run_id']}/audit.jsonl")


if __name__ == "__main__":
    main()
