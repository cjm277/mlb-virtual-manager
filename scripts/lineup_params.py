"""Two numbers the win-model lineup needs, measured on every 2026 start (no LLM, about 2 minutes):

1. Matchup shrink (lambda): how much of the app's pitch-type matchup adjustment shows up in real results.
   For every hitter who started, compare how he actually hit against the opposing starter's hand that day with
   two pre-game numbers: his season value in the win model (regressed wOBA + platoon edge + the starter's
   quality), and the pitch-type adjustment (the matchup engine's score minus the same engine without pitch
   types). lambda = how much a point of adjustment is worth relative to a point of season value. 0 means the
   pitch-type detail adds nothing; 1 means take it at face value.
2. Fatigue cost: how much worse a hitter past the rest-day threshold (6 straight starts for catchers, 10 for
   others) hits than his pre-game value says, in wOBA points.

Writes data/lineup_params.json (read by backend/engine/winmodel.py) and evidence/tests/lineup_params.md.
"""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import db  # noqa: E402
from backend.engine.hitting import batter_split  # noqa: E402
from backend.engine.matchups import batting_side  # noqa: E402
from backend.engine.pitching import pitcher_split  # noqa: E402
from backend.engine.workload import REST_AFTER  # noqa: E402

OUT = ROOT / "data" / "lineup_params.json"
REPORT = ROOT / "evidence" / "tests" / "lineup_params.md"
BOOT = 500


@lru_cache(maxsize=None)
def b_vs_hand(pid: int, d: str, hand: str) -> float | None:
    return batter_split(pid, d, hand, keys=["xwoba"])["xwoba"]


@lru_cache(maxsize=None)
def p_vs_side(pid: int, d: str, side: str) -> float | None:
    return pitcher_split(pid, d, side)["xwoba"]


def streaks() -> dict[tuple[int, int], int]:
    """(game_pk, player_id) -> team games in a row he had started before this one."""
    out: dict[tuple[int, int], int] = {}
    for t in [r["team_id"] for r in db.rows("SELECT team_id FROM teams")]:
        games = db.rows("SELECT DISTINCT game_pk, game_date FROM batting_lines WHERE team_id = ? ORDER BY game_date, game_pk", t)
        starters = {}
        for r in db.rows("SELECT game_pk, player_id FROM batting_lines WHERE team_id = ? AND is_starter = 1", t):
            starters.setdefault(r["game_pk"], set()).add(r["player_id"])
        run: dict[int, int] = {}
        for g in games:
            s = starters.get(g["game_pk"], set())
            for pid in s:
                out[(g["game_pk"], pid)] = run.get(pid, 0)
            run = {pid: run.get(pid, 0) + 1 for pid in s}
    return out


def wls(X: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    W = np.sqrt(w)
    return np.linalg.lstsq(X * W[:, None], y * W, rcond=None)[0]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import win_model as wm
    wm.load_constants()
    rows = json.loads(wm.FEATURES.read_text(encoding="utf-8"))
    run = streaks()
    pos = {(r["game_pk"], r["player_id"]): r["start_position"] for r in db.rows(
        "SELECT game_pk, player_id, start_position FROM batting_lines WHERE is_starter = 1")}
    outcome = {(r["game_pk"], r["batter_id"], r["p_throws"]): (r["num"], r["den"]) for r in db.rows(
        "SELECT game_pk, batter_id, p_throws, SUM(woba_num) num, SUM(woba_den) den FROM statcast_batter_game "
        "GROUP BY 1, 2, 3")}
    adv, same = wm.platoon_split()
    data = []
    for g in rows:
        d = g["date"]
        for side, other in (("home", "away"), ("away", "home")):
            sp = g[other]["sp"]
            hand = wm.hand(sp["pid"])[1] or "R"
            for e in g[side]["lineup"]:
                num, den = outcome.get((g["game_pk"], e["pid"], hand), (0, 0))
                if not den:
                    continue
                season = (wm.shrink(e["woba"], e["n"], 200) + (adv if e["edge"] else same)
                          + wm.shrink(sp["woba"], sp["n"], 400) - wm.LEAGUE)
                bx, px = b_vs_hand(e["pid"], d, hand), p_vs_side(sp["pid"], d, batting_side(wm.hand(e["pid"])[0], hand))
                base = ((bx if bx is not None else wm.LG_XWOBA) + (px if px is not None else wm.LG_XWOBA)) / 2
                limit = REST_AFTER["C" if pos.get((g["game_pk"], e["pid"])) == "C" else "other"]
                tired = run.get((g["game_pk"], e["pid"]), 0) >= limit
                data.append((num / den, den, season, e["mx"] - base, float(tired)))
    a = np.array(data)
    y, w = a[:, 0], a[:, 1]
    X = np.column_stack([np.ones(len(a)), a[:, 2], a[:, 3], a[:, 4]])
    b = wls(X, y, w)
    rng = np.random.default_rng(409)
    draws = np.array([wls(X[i], y[i], w[i]) for i in (rng.integers(0, len(a), len(a)) for _ in range(BOOT))])
    lam_draws = draws[:, 2] / draws[:, 1]
    lam = float(np.clip(b[2] / b[1], 0, 1))
    res = {
        "hitter_games": len(a), "plate_appearances": int(w.sum()),
        "season_value_slope": float(b[1]), "season_value_ci": np.percentile(draws[:, 1], [2.5, 97.5]).tolist(),
        "pitch_type_slope": float(b[2]), "pitch_type_ci": np.percentile(draws[:, 2], [2.5, 97.5]).tolist(),
        "matchup_lambda": lam, "matchup_lambda_raw": float(b[2] / b[1]),
        "matchup_lambda_ci": np.percentile(lam_draws, [2.5, 97.5]).tolist(),
        "fatigue_woba": float(b[3]), "fatigue_ci": np.percentile(draws[:, 3], [2.5, 97.5]).tolist(),
        "tired_share": float(a[:, 4].mean()),
    }
    OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    md = "\n".join([
        "# Lineup model parameters, measured on 2026",
        "",
        f"Every 2026 start: {res['hitter_games']:,} hitter-games, {res['plate_appearances']:,} plate appearances against "
        "the opposing starter's hand. Outcome: how the hitter actually hit (wOBA) that day. Weighted least squares, "
        f"95% ranges from {BOOT} bootstrap resamples. Script: `scripts/lineup_params.py`.",
        "",
        "| Pre-game input | Effect on how he actually hit | 95% range |",
        "|---|---|---|",
        f"| Season value in the win model (per 1.000) | {res['season_value_slope']:.3f} | "
        f"{res['season_value_ci'][0]:.3f} to {res['season_value_ci'][1]:.3f} |",
        f"| Pitch-type matchup adjustment (per 1.000) | {res['pitch_type_slope']:.3f} | "
        f"{res['pitch_type_ci'][0]:.3f} to {res['pitch_type_ci'][1]:.3f} |",
        f"| Past the rest-day threshold ({res['tired_share']:.1%} of starts) | {res['fatigue_woba']:+.4f} wOBA | "
        f"{res['fatigue_ci'][0]:+.4f} to {res['fatigue_ci'][1]:+.4f} |",
        "",
        f"**Matchup shrink:** a point of pitch-type adjustment is worth {res['matchup_lambda_raw']:.2f} of a point of season "
        f"value (95% range {res['matchup_lambda_ci'][0]:.2f} to {res['matchup_lambda_ci'][1]:.2f}). The app now keeps "
        f"{res['matchup_lambda']:.0%} of the adjustment (clipped to 0-100%).",
        "",
        f"**Fatigue cost:** a hitter past the threshold hits {res['fatigue_woba']:+.4f} wOBA against his pre-game value. "
        "The lineup model charges that against a tired hitter's value for the day.",
        "",
    ])
    REPORT.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
