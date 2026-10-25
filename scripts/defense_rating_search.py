"""How should a defensive rating be built so it predicts next season's defense? (no LLM, seconds)

For each target season (2025 and 2026), predict every fielder's fielding runs per 9 innings at each position
from the seasons BEFORE it only, and compare with what he actually did, weighted by innings played. Same for
catcher framing per pitch. Candidates: last season only vs the last three seasons weighted toward the most
recent, and how hard to regress toward average. The winner goes to data/lineup_params.json ("defense_rating").
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.engine import defense  # noqa: E402

PARAMS = ROOT / "data" / "lineup_params.json"
REPORT = ROOT / "evidence" / "tests" / "defense_rating_search.md"
TARGETS = (2025, 2026)
WEIGHTS = {"last season only": [1.0], "3 seasons, 1 / 0.8 / 0.6": [1.0, 0.8, 0.6], "3 seasons, 1 / 0.6 / 0.3": [1.0, 0.6, 0.3],
           "3 seasons, equal": [1.0, 1.0, 1.0]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    fld = db.rows("SELECT season, player_id, position, fielding_runs_prevented frp, innings FROM fielding_by_position "
                  "WHERE season IN (2025, 2026) AND innings >= 50 AND frp IS NOT NULL")
    frm = db.rows("SELECT season, player_id, framing_runs fr, pitches FROM framing_history WHERE season IN (2025, 2026) AND pitches >= 500")
    rows = []
    for name, wts in WEIGHTS.items():
        for k in (100, 300, 600, 1000, 1500, 2500):
            s = {"season_weights": wts, "k_innings": k, "k_pitches": 3000}
            y = np.array([9 * r["frp"] / r["innings"] for r in fld]); w = np.array([r["innings"] for r in fld])
            p = np.array([defense.fielding_per_game(r["player_id"], r["position"], r["season"] - 1, s) for r in fld])
            mse, base = np.average((y - p) ** 2, weights=w), np.average(y ** 2, weights=w)
            corr = np.corrcoef(p, y)[0, 1] if p.std() else 0.0
            rows.append(("fielding", name, k, 1 - mse / base, corr, wts))
        for k in (500, 1500, 3000, 6000, 12000):
            s = {"season_weights": wts, "k_innings": 600, "k_pitches": k}
            y = np.array([defense.PITCHES_PER_GAME * r["fr"] / r["pitches"] for r in frm]); w = np.array([r["pitches"] for r in frm])
            p = np.array([defense.framing_per_game(r["player_id"], r["season"] - 1, s) for r in frm])
            mse, base = np.average((y - p) ** 2, weights=w), np.average(y ** 2, weights=w)
            corr = np.corrcoef(p, y)[0, 1] if p.std() else 0.0
            rows.append(("framing", name, k, 1 - mse / base, corr, wts))
    best_f = max((r for r in rows if r[0] == "fielding"), key=lambda r: r[3])
    best_c = max((r for r in rows if r[0] == "framing" and r[5] == best_f[5]), key=lambda r: r[3])
    # What fielders with no history at a position actually did there (innings-weighted, per 9 innings).
    priors = {"new_position": [0.0, 0.0], "no_history": [0.0, 0.0]}
    for r in db.rows("""SELECT f.player_id, f.position, f.season, COALESCE(f.fielding_runs_prevented, 0) frp, f.innings,
                          (SELECT SUM(h.innings) FROM fielding_by_position h WHERE h.player_id = f.player_id
                             AND h.position = f.position AND h.season BETWEEN f.season - 3 AND f.season - 1) here,
                          (SELECT SUM(h.innings) FROM fielding_by_position h WHERE h.player_id = f.player_id
                             AND h.season BETWEEN f.season - 3 AND f.season - 1) anywhere
                        FROM fielding_by_position f WHERE f.season IN (2025, 2026) AND f.innings > 0"""):
        if r["here"]:
            continue
        k = "new_position" if r["anywhere"] else "no_history"
        priors[k][0] += r["frp"]; priors[k][1] += r["innings"]
    prior = {k: 9 * v[0] / v[1] for k, v in priors.items()}
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    params["defense_rating"] = {"season_weights": best_f[5], "k_innings": best_f[2], "k_pitches": best_c[2],
                                "new_position_per_game": prior["new_position"], "no_history_per_game": prior["no_history"]}
    PARAMS.write_text(json.dumps(params, indent=2), encoding="utf-8")
    md = ["# Building a defensive rating that predicts next season", "",
          f"Targets: every fielder-position with 50+ innings ({len(fld):,}) and catcher with 500+ pitches ({len(frm)}) in 2025 "
          "and 2026, predicted only from earlier seasons (2023 onward). \"Skill explained\" = 1 − weighted squared error / "
          "weighted squared rating (higher is better; 0 = no better than calling everyone average). Script: "
          "`scripts/defense_rating_search.py`.", "",
          "| Rating | Seasons | Regress at | Skill explained | Correlation with next season |", "|---|---|---|---|---|"]
    for kind in ("fielding", "framing"):
        for r in sorted((r for r in rows if r[0] == kind), key=lambda r: -r[3])[:6]:
            unit = "innings" if kind == "fielding" else "pitches"
            md.append(f"| {kind} | {r[1]} | {r[2]:,} {unit} | {r[3]:.3f} | {r[4]:.2f} |")
        last = max((r for r in rows if r[0] == kind and r[1] == "last season only"), key=lambda r: r[3])
        md.append(f"| {kind} (best using last season only) | last season only | {last[2]:,} | {last[3]:.3f} | {last[4]:.2f} |")
    md += ["", f"**Chosen:** seasons weighted {best_f[5]}, fielding regressed at {best_f[2]:,} innings, framing at "
           f"{best_c[2]:,} pitches.", "",
           "**Players with no history at a position** (what such fielders actually did there in 2025-2026, per 9 innings): "
           f"new to the position but played elsewhere {prior['new_position']:+.4f} runs ({priors['new_position'][1]:,.0f} "
           f"innings); no MLB fielding history at all {prior['no_history']:+.4f} runs ({priors['no_history'][1]:,.0f} "
           "innings). These replace \"assume average\" for unrated players.", ""]
    REPORT.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
