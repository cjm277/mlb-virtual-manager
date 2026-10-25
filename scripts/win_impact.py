"""Win impact: would the staff's game plans win more games than the real managers' choices?

We can never watch a game played with our plan, so this is a two-stage estimate:
  1. Win model (no LLM). On every 2026 game, learn what a lineup and a starting pitcher are worth in wins from
     what really happened: a logistic regression of "home team won" on the two lineups' and two starters'
     quality, using only stats from before the game. Tested out of sample (fit on April-June, test on
     July-September).
  2. Counterfactual. For a random sample of games, the staff builds its plan exactly as the app does. We then
     score our lineup and starter and the real manager's lineup and starter with the same win model, holding
     the opponent fixed (their real lineup and starter). The gap is the change in win probability.

Two ways to grade a lineup, so the app isn't only graded on its own homework:
  - "results": each hitter's wOBA to date (what actually happened), shrunk toward league average for small
    samples, with the league-typical platoon edge. The app never optimizes this number directly.
  - "matchup": the app's own matchup engine (expected xwOBA against this starter's pitch mix).

Usage:
  python scripts/win_impact.py plans [--n-per-team 5] [--concurrency 4]   # build the sample plans (costs money)
  python scripts/win_impact.py features                                   # stage-1 data for every game (slow, free)
  python scripts/win_impact.py report                                     # score the staff's plans, write the report
  python scripts/win_impact.py plans --version v2                         # rebuild the sample with the win-model lineup
  python scripts/win_impact.py compare                                    # before (v1) vs after (v2), same games
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import config, db  # noqa: E402

SAVE = ROOT / "evidence" / "logs" / "win_impact"
PLANS = SAVE / "plans"
SEED = 409
WINDOW = ("2026-04-15", "2026-09-27")


# ---------------------------------------------------------------------------
# Sample and plans
# ---------------------------------------------------------------------------

def sample_games(n_per_team: int = 5) -> list[dict]:
    """n games per team, managed by that team, spread evenly over the window (one per date bucket)."""
    rng = random.Random(SEED)
    teams = [r["team_id"] for r in db.rows("SELECT team_id FROM teams ORDER BY team_id")]
    chosen = []
    for t in teams:
        games = db.rows("SELECT game_pk, game_date, home_team_id, away_team_id FROM games WHERE game_date BETWEEN ? AND ? "
                        "AND (home_team_id = ? OR away_team_id = ?) ORDER BY game_date, game_pk", *WINDOW, t, t)
        k = len(games) // n_per_team
        for i in range(n_per_team):
            g = dict(rng.choice(games[i * k:(i + 1) * k]))
            g["team_id"] = t
            g["opponent_id"] = g["away_team_id"] if g["home_team_id"] == t else g["home_team_id"]
            chosen.append(g)
    return chosen


def build_plans(n_per_team: int, concurrency: int, out: Path = PLANS, limit: int | None = None) -> None:
    from backend.agents.team import build_game_plan

    config.RUNS_DIR = out
    games = sample_games(n_per_team)[:limit]
    sem = asyncio.Semaphore(concurrency)
    done = {"n": 0, "cost": 0.0}

    async def one(g: dict) -> None:
        run_id = f"{g['game_date']}_g{g['game_pk']}_t{g['team_id']}"
        if (out / run_id / "plan.json").exists():
            return
        async with sem:
            try:
                plan = await build_game_plan(g["game_pk"], g["team_id"], run_id=run_id)
            except Exception as exc:          # one failed plan must not stop the sample
                print(f"  {run_id}: FAILED {type(exc).__name__}: {exc}", flush=True)
                return
            done["n"] += 1
            done["cost"] += plan["usage"]["total"]["cost_usd"]
            print(f"  [{done['n']}] {run_id}: {plan['status']} {plan['usage']['seconds']}s "
                  f"${plan['usage']['total']['cost_usd']:.4f} (running total ${done['cost']:.2f})", flush=True)

    async def main() -> None:
        await asyncio.gather(*(one(g) for g in games))

    print(f"Building {len(games)} plans, {concurrency} at a time")
    asyncio.run(main())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["plans", "features", "report", "compare"])
    ap.add_argument("--n-per-team", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--version", default="v1", help="v1 = plans/ (before the win-model lineup), v2 = plans_v2/ (after)")
    ap.add_argument("--limit", type=int, help="only the first N sampled games (smoke test)")
    args = ap.parse_args()
    if args.step == "plans":
        build_plans(args.n_per_team, args.concurrency, PLANS if args.version == "v1" else SAVE / f"plans_{args.version}",
                    args.limit)
    elif args.step == "features":
        from win_model import build_features
        build_features()
    elif args.step == "report":
        from win_model import write_report
        write_report()
    else:
        from win_model import write_comparison
        write_comparison()


if __name__ == "__main__":
    main()
