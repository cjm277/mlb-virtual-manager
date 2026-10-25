"""How much is a fielder's rating worth when he has little history at the position? Fitted WITHOUT 2026 data (no LLM).

For every 2025 player-position (outfield and infield; catchers are framing), his pre-2025 rating (the app's rating
built from 2023-24 only, exactly as a 2025 game would see it) against what he did there in 2025, innings-weighted,
by how established he was at that position before 2025:
  established  300+ innings there in the prior seasons
  part-time    1-299 innings there
  new          none (rated by the app's out-of-position / no-history prior)
E[2025 runs saved per game | rating, group] = intercept + slope x rating. The optimizer prices each fielder at this
expected value, with the slope capped at 1 so a thin record is never amplified ("calibrated"). A stricter variant
gives part-time and new fielders only their group's average, with no credit for their own thin record ("strict").
The 2026 fit is shown for comparison only; nothing from 2026 is used.

Writes data/lineup_params.json "defense_caution" and evidence/tests/defense_caution.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.engine import defense as dfn  # noqa: E402

PARAMS = ROOT / "data" / "lineup_params.json"
REPORT = ROOT / "evidence" / "tests" / "defense_caution.md"


def fit(season: int, rng: np.random.Generator) -> dict:
    rows = db.rows("SELECT player_id, position, innings, fielding_runs_prevented frp FROM fielding_by_position "
                   "WHERE season = ? AND innings > 0 AND position NOT IN ('C', 'DH', 'P')", season)
    groups: dict[str, list] = {}
    for r in rows:
        b = dfn.experience_group(r["player_id"], r["position"], season - 1)
        groups.setdefault(b, []).append((dfn.fielding_per_game(r["player_id"], r["position"], season - 1),
                                         9 * (r["frp"] or 0.0) / r["innings"], r["innings"]))
    out = {}
    for b, v in groups.items():
        a = np.array(v)

        def wls(i):
            A = np.column_stack([np.ones(len(i)), a[i, 0]])
            W = a[i, 2]
            return np.linalg.solve(A.T @ (A * W[:, None]) + 1e-9 * np.eye(2), A.T @ (W * a[i, 1]))

        co = wls(np.arange(len(a)))
        draws = np.array([wls(rng.integers(0, len(a), len(a))) for _ in range(1000)])
        small = a[a[:, 2] < 100]
        out[b] = {"intercept": float(co[0]), "slope": float(co[1]), "n": len(a),
                  "intercept_ci": np.percentile(draws[:, 0], [2.5, 97.5]).tolist(),
                  "slope_ci": np.percentile(draws[:, 1], [2.5, 97.5]).tolist(),
                  "mean_rating": float(np.average(a[:, 0], weights=a[:, 2])),
                  "mean_result": float(np.average(a[:, 1], weights=a[:, 2])),
                  "under_100_innings": {"n": len(small), "mean_result_unweighted": float(small[:, 1].mean()) if len(small) else None,
                                        "mean_result_weighted": float(np.average(small[:, 1], weights=small[:, 2])) if len(small) else None}}
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rng = np.random.default_rng(409)
    f25, f26 = fit(2025, rng), fit(2026, rng)
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    params["defense_caution"] = {b: {"intercept": v["intercept"], "slope": min(v["slope"], 1.0), "mean": v["mean_result"]}
                                 for b, v in f25.items()}
    PARAMS.write_text(json.dumps(params, indent=2), encoding="utf-8")
    G = ["established", "part-time", "new"]
    md = [
        "# Pricing fielders with a thin record at the position (fitted on 2025, no 2026 data)",
        "",
        "Every 2025 player-position: the app's pre-2025 rating (2023-24 only) against what he did there in 2025, "
        "innings-weighted, by how established he was there. Script: `scripts/defense_caution.py`. Runs saved per game.",
        "",
        "| Group | Player-positions | Mean rating | Mean 2025 result | Intercept | Slope | 2026 fit (comparison only): intercept / slope |",
        "|---|---|---|---|---|---|---|",
        *[f"| {g} | {f25[g]['n']} | {f25[g]['mean_rating']:+.4f} | {f25[g]['mean_result']:+.4f} | "
          f"{f25[g]['intercept']:+.4f} ({f25[g]['intercept_ci'][0]:+.4f} to {f25[g]['intercept_ci'][1]:+.4f}) | "
          f"{f25[g]['slope']:.2f} ({f25[g]['slope_ci'][0]:.2f} to {f25[g]['slope_ci'][1]:.2f}) | "
          f"{f26[g]['intercept']:+.4f} / {f26[g]['slope']:.2f} |" for g in G],
        "",
        "**Small samples look far worse than they are.** Player-positions with fewer than 100 innings that season:",
        "",
        "| Group | Season | n | Mean result, each player counted once | Mean result, innings-weighted |",
        "|---|---|---|---|---|",
        *[f"| {g} | {s} | {F[g]['under_100_innings']['n']} | {F[g]['under_100_innings']['mean_result_unweighted']:+.3f} | "
          f"{F[g]['under_100_innings']['mean_result_weighted']:+.3f} |" for g in G for s, F in ((2025, f25), (2026, f26))],
        "",
        "Counted once each, short stints average far below zero (-0.13 to -0.19 runs a game for part-time and new "
        "fielders). Weighted by innings the gap shrinks by half or more but stays clearly negative (-0.03 to -0.07), well "
        "below their ratings, in both seasons. Two things produce this, and the data can't fully separate them: a fielder "
        "who starts badly at a position is moved off it, freezing a bad small sample (a measurement effect); and managers "
        "see things the ratings don't, so short stints go to fielders who really are worse there. Note the short stint is "
        "itself an outcome: before the game no one knows whose stint will be short, which is why the groups above, by "
        "pre-game experience and all innings, are what the optimizer can use.",
        "",
        "**Used by the optimizer** (data/lineup_params.json `defense_caution`, slope capped at 1): calibrated = intercept + "
        "slope x rating for each group; strict = established as calibrated, part-time and new at their group's mean.",
        "",
    ]
    REPORT.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
