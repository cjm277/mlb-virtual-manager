"""Turn the starting-pitcher predictor's track record into honest percentages for the app.

A prediction counts as right if that pitcher took the team's turn: he started, or he pitched the bulk
innings after an opener. Two tables are measured on every 2026 game (no LLM, no cost):

  live_2026               the live predictor (used for 2026 games), by its confidence label, split out for
                          the early season (when the rotation is filled in from 2025)
  projection_by_games_in  a PRESEASON projection of 2026, the same kind of call the app makes for 2027:
                          each team's Opening Day roster, ranked by 2025 starts, cycled through the schedule.
                          Measured by how far into the season the game is, because it gets worse the further
                          out you project.

Usage:
  python scripts/calibrate_starter.py
Writes:
  data/starter_calibration.json            (read by the app)
  evidence/tests/phase5_starter_calibration.md
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db  # noqa: E402
from backend.engine.roster import active_roster, is_pitcher  # noqa: E402
from backend.engine.rotation import (CALIBRATION_FILE, PROJECTION_BUCKETS, predict_starter, projection_bucket,  # noqa: E402
                                     turn_taker)

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence" / "tests" / "phase5_starter_calibration.md"


def took_turn(game_pk: int, team_id: int, pick: int | None) -> bool:
    starter = db.one("SELECT player_id FROM pitching_lines WHERE game_pk = ? AND team_id = ? AND is_starter = 1",
                     game_pk, team_id)
    return pick is not None and pick in {starter["player_id"] if starter else None, turn_taker(game_pk, team_id)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    started = time.time()
    games = db.rows("SELECT game_pk, game_date, game_number, home_team_id, away_team_id FROM games "
                    "ORDER BY game_date, game_number")

    # (A) The live predictor, by confidence label.
    live: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for g in games:
        for team in (g["home_team_id"], g["away_team_id"]):
            p = predict_starter(team, g["game_date"], g["game_number"])
            ok = took_turn(g["game_pk"], team, p["predicted"]["player_id"] if p["predicted"] else None)
            keys = [p["confidence"], "all"]
            if "early season" in p["method"]:
                keys.append(p["confidence"] + "_early")
            for k in keys:
                live[k][0] += ok
                live[k][1] += 1

    # (B) A preseason projection of 2026 (the 2027-style call), by games into the season.
    proj: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for t in db.rows("SELECT team_id FROM teams"):
        tid = t["team_id"]
        team_games = db.rows("""SELECT game_pk, game_date FROM games WHERE home_team_id = ?1 OR away_team_id = ?1
                                ORDER BY game_date, game_number""", tid)
        opening = {r["player_id"] for r in active_roster(tid, team_games[0]["game_date"]) if is_pitcher(r)}
        gs25 = {r["player_id"]: r["gs"] for r in db.rows(
            "SELECT player_id, MAX(gs) gs FROM season_pitching WHERE season = 2025 GROUP BY player_id")}
        rotation = sorted((p for p in opening if gs25.get(p, 0) >= 5), key=lambda p: -gs25[p])[:5]
        if not rotation:
            continue
        for n, g in enumerate(team_games):
            ok = took_turn(g["game_pk"], tid, rotation[n % len(rotation)])
            for k in (projection_bucket(n + 1), "all"):
                proj[k][0] += ok
                proj[k][1] += 1

    table = lambda d: {k: {"rate": round(v[0] / v[1], 4), "n": v[1]} for k, v in d.items() if v[1]}  # noqa: E731
    out = {
        "definition": "Right if the predicted pitcher started the game or pitched the bulk innings after an opener.",
        "generated": datetime.now().isoformat(timespec="seconds"),
        "live_2026": table(live),
        "projection_by_games_in": table(proj),
    }
    CALIBRATION_FILE.write_text(json.dumps(out, indent=2), encoding="utf-8")

    pct = lambda c: f"{100 * c['rate']:.1f}%"  # noqa: E731
    lines = [
        "# Starting-pitcher prediction: how sure are we?",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} by `scripts/calibrate_starter.py` over every 2026 game. "
        "A prediction counts as **right if that pitcher started, or pitched the bulk innings after an opener**. "
        "The app shows these rates as the percentage next to every predicted starter.",
        "",
        "## 2026 games (live predictor)",
        "",
        "| Confidence label | Right | Predictions |",
        "|---|---|---|",
        *[f"| {k.replace('_early', ' (early season)')} | {pct(v)} | {v['n']:,} |"
          for k, v in sorted(out["live_2026"].items())],
        "",
        "## 2027 games (preseason projection, measured on 2026)",
        "",
        "The 2027 starter is a projection made before the season: Opening Day roster, ranked by the prior season's "
        "starts, cycled through the schedule. Doing exactly that for 2026 and checking it against what happened:",
        "",
        "| Games into the season | Right | Predictions |",
        "|---|---|---|",
        *[f"| {k} | {pct(out['projection_by_games_in'][k])} | {out['projection_by_games_in'][k]['n']:,} |"
          for k in [f"{lo}-{hi}" for lo, hi in PROJECTION_BUCKETS] + ["all"] if k in out["projection_by_games_in"]],
        "",
        f"Runtime {time.time() - started:.0f}s.",
        "",
    ]
    EVIDENCE.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
