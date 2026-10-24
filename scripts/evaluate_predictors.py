"""Measure the rotation and lineup predictors on every 2026 game (no LLM, no cost).

For each game and each team, predict using only data from before the game, then compare to what
actually happened in the box score. MLB's own listed probable starter is scored too, as a benchmark.

Usage:
  python scripts/evaluate_predictors.py
Writes:
  evidence/tests/phase3_predictor_accuracy.md
"""

from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db  # noqa: E402
from backend.engine.lineup import predict_lineup  # noqa: E402
from backend.engine.rotation import predict_starter  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "evidence" / "tests" / "phase3_predictor_accuracy.md"


def pct(a: float, b: float) -> str:
    return f"{100 * a / b:.1f}%" if b else "n/a"


def main() -> None:
    started = time.time()
    games = db.rows("SELECT game_pk, game_date, game_number, home_team_id, away_team_id, home_probable_id, "
                    "away_probable_id FROM games ORDER BY game_date, game_number")
    actual_sp = {(r["game_pk"], r["team_id"]): r["player_id"] for r in
                 db.rows("SELECT game_pk, team_id, player_id FROM pitching_lines WHERE is_starter = 1")}
    hand = {r["player_id"]: r["pitch_hand"] for r in db.rows("SELECT player_id, pitch_hand FROM players")}
    lineups = defaultdict(dict)
    for r in db.rows("SELECT game_pk, team_id, player_id, lineup_slot, start_position FROM batting_lines WHERE is_starter = 1"):
        lineups[(r["game_pk"], r["team_id"])][r["player_id"]] = (r["lineup_slot"], r["start_position"])

    sp = defaultdict(lambda: [0, 0])          # bucket -> [correct, total]
    mlb = [0, 0]
    top2 = [0, 0]
    first_start = 0
    lu_overlap, lu_8plus, lu_pos, lu_pos_n, lu_slot, n_lu = 0, 0, 0, 0, 0, 0

    for i, g in enumerate(games, 1):
        for team, opp, probable in ((g["home_team_id"], g["away_team_id"], g["home_probable_id"]),
                                    (g["away_team_id"], g["home_team_id"], g["away_probable_id"])):
            actual = actual_sp.get((g["game_pk"], team))
            if actual is None:
                continue
            pred = predict_starter(team, g["game_date"], g["game_number"])
            pick = pred["predicted"]["player_id"] if pred["predicted"] else None
            ok = pick == actual
            month = g["game_date"][:7]
            for bucket in ("all", f"month {month}", f"confidence {pred['confidence']}"):
                sp[bucket][0] += ok
                sp[bucket][1] += 1
            names = {c["name"]: c["player_id"] for c in pred["rotation_considered"]}
            ranked = [pick] + [names.get(n) for n in pred["next_most_likely"][:1]]
            top2[0] += actual in ranked
            top2[1] += 1
            if probable:
                mlb[0] += probable == actual
                mlb[1] += 1
            had_started = db.one("SELECT 1 FROM pitching_lines WHERE player_id = ? AND is_starter = 1 AND game_date < ? "
                                 "LIMIT 1", actual, g["game_date"])
            first_start += not had_started

            # Lineup: predicted against the actual opposing starter's hand (in the app, our chosen starter's hand).
            real = lineups.get((g["game_pk"], team))
            opp_sp = actual_sp.get((g["game_pk"], opp))
            if real and len(real) == 9:
                lu = predict_lineup(team, g["game_date"], vs_hand=hand.get(opp_sp))
                predicted = {x["player_id"]: (x["slot"], x["position"]) for x in lu["lineup"]}
                common = set(predicted) & set(real)
                lu_overlap += len(common)
                lu_8plus += len(common) >= 8
                lu_pos += sum(predicted[p][1] == real[p][1] for p in common)
                lu_slot += sum(predicted[p][0] == real[p][0] for p in common)
                lu_pos_n += len(common)
                n_lu += 1
        if i % 250 == 0:
            print(f"  {i}/{len(games)} games ({time.time() - started:.0f}s)", flush=True)

    total = sp["all"][1]
    lines = [
        "# Phase 3 predictor accuracy",
        "",
        f"Run {datetime.now():%Y-%m-%d %H:%M} by `scripts/evaluate_predictors.py` over every 2026 regular-season game "
        f"({len(games):,} games, {total:,} team-games). Each prediction uses only data from before that game; "
        "no LLM is involved, so this costs nothing to run.",
        "",
        "## Starting pitcher (rotation predictor)",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| **Predicted starter actually started** | **{pct(*sp['all'])}** ({sp['all'][0]:,} of {total:,}) |",
        f"| Actual starter was one of our top 2 on-turn pitchers | {pct(*top2)} |",
        f"| Benchmark: MLB's own listed probable starter was right | {pct(*mlb)} ({mlb[1]:,} games with a listing) |",
        f"| Games where the actual starter had never started before that season (call-ups, openers; unpredictable from rotation order) | {pct(first_start, total)} |",
        "",
        "By confidence label and month:",
        "",
        "| Bucket | Accuracy | Team-games |",
        "|---|---|---|",
        *[f"| {b} | {pct(*v)} | {v[1]:,} |" for b, v in sorted(sp.items()) if b != "all"],
        "",
        "## Opponent lineup (lineup predictor)",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Average predicted starters who actually started (out of 9) | **{lu_overlap / n_lu:.2f}** |",
        f"| Games with 8 or 9 of 9 right | {pct(lu_8plus, n_lu)} |",
        f"| Correct position, for players we got right | {pct(lu_pos, lu_pos_n)} |",
        f"| Exact batting-order slot, for players we got right | {pct(lu_slot, lu_pos_n)} |",
        "",
        f"Lineups scored: {n_lu:,} team-games. Runtime {time.time() - started:.0f}s.",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
