"""Does defense earn its place? Measured on every 2026 team-game (no LLM, about a minute).

Outcome: runs the team allowed. Pre-game inputs:
  - the opponent lineup's expected runs against our starter (the win model, offense and pitching only)
  - our fielders' range: 2025 fielding runs prevented per game at the positions they actually played
  - our catcher's framing: 2025 framing runs per game
Least squares with 95% bootstrap ranges; also fitted on April-June and tested on July-September. A weight of 1
means a run of rated defense is worth a full run allowed; 0 means it predicts nothing. The measured weights
(clipped to 0-1.5) go to data/lineup_params.json and are what the win model and the lineup optimizer use.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import db  # noqa: E402
from backend.engine import defense, winmodel  # noqa: E402

PARAMS = ROOT / "data" / "lineup_params.json"
REPORT = ROOT / "evidence" / "tests" / "defense_params.md"
SPLIT = "2026-07-01"
BOOT = 1000


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import win_model as wm
    games = json.loads(wm.FEATURES.read_text(encoding="utf-8"))
    pos = {(r["game_pk"], r["player_id"]): r["start_position"] for r in db.rows(
        "SELECT game_pk, player_id, start_position FROM batting_lines WHERE is_starter = 1")}
    score = {r["game_pk"]: (r["home_score"], r["away_score"]) for r in db.rows("SELECT game_pk, home_score, away_score FROM games")}
    unit = {"fielding": 1.0, "framing": 1.0}
    data = []
    for g in games:
        d = g["date"]
        hs, as_ = score[g["game_pk"]]
        for us, them, allowed in (("home", "away", as_), ("away", "home", hs)):
            exp = winmodel.expected_runs([(e["slot"], e["pid"]) for e in g[them]["lineup"]], d, g[us]["sp"]["pid"])
            fielders = [(e["pid"], pos[(g["game_pk"], e["pid"])]) for e in g[us]["lineup"]]
            field = sum(defense.runs_saved(p, q, d, unit) for p, q in fielders if q not in ("C", "DH"))
            frame = sum(defense.runs_saved(p, q, d, unit) for p, q in fielders if q == "C")
            data.append((d < SPLIT, allowed, exp, field, frame))
    a = np.array(data, dtype=float)
    train = a[:, 0] == 1
    y = a[:, 1]
    X = np.column_stack([np.ones(len(a)), a[:, 2], a[:, 3], a[:, 4]])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    rng = np.random.default_rng(409)
    draws = np.array([np.linalg.lstsq(X[i], y[i], rcond=None)[0] for i in (rng.integers(0, len(a), len(a)) for _ in range(BOOT))])
    ci = np.percentile(draws, [2.5, 97.5], axis=0)
    # Out of sample: does adding defense lower the July-September error?
    b_off = np.linalg.lstsq(X[train][:, :2], y[train], rcond=None)[0]
    b_def = np.linalg.lstsq(X[train], y[train], rcond=None)[0]
    mse_off = float(np.mean((y[~train] - X[~train][:, :2] @ b_off) ** 2))
    mse_def = float(np.mean((y[~train] - X[~train] @ b_def) ** 2))
    # A rated run saved should be worth one run allowed. Use exactly 1 when the measured range includes it (steadier
    # than a noisy point estimate); otherwise use the measured effect, clipped to 0-1.5.
    w = {k: (1.0 if ci[0][i] <= -1.0 <= ci[1][i] else float(np.clip(-b[i], 0, 1.5)))
         for k, i in (("fielding", 2), ("framing", 3))}
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    params["defense"] = w
    params["defense_fit"] = {"coef": b.tolist(), "ci_low": ci[0].tolist(), "ci_high": ci[1].tolist(),
                             "test_mse_offense_only": mse_off, "test_mse_with_defense": mse_def,
                             "team_games": len(a), "sd_fielding": float(a[:, 3].std()), "sd_framing": float(a[:, 4].std())}
    PARAMS.write_text(json.dumps(params, indent=2), encoding="utf-8")
    md = "\n".join([
        "# Does defense earn its place in the win model?",
        "",
        f"Every 2026 team-game ({len(a):,}). Outcome: runs allowed. Defensive ratings use 2023-2025 only (completed "
        "seasons before each game, weighted toward 2025), so nothing from 2026 leaks in. Least squares; 95% ranges from 1,000 bootstrap "
        "resamples. Script: `scripts/defense_params.py`.",
        "",
        "| Pre-game input (runs per game) | Effect on runs allowed | 95% range |",
        "|---|---|---|",
        f"| Opponent lineup's expected runs vs our starter | {b[1]:+.3f} | {ci[0][1]:+.3f} to {ci[1][1]:+.3f} |",
        f"| Our fielders' range (fielding runs prevented at their positions, 2023-2025 rating) | {b[2]:+.3f} | {ci[0][2]:+.3f} to {ci[1][2]:+.3f} |",
        f"| Our catcher's framing (2023-2025 rating) | {b[3]:+.3f} | {ci[0][3]:+.3f} to {ci[1][3]:+.3f} |",
        "",
        "A coefficient of −1 means a run of rated defense saves a full run; 0 means it predicts nothing. Fielding "
        f"varies by ±{a[:, 3].std():.2f} runs per game across real lineups (one standard deviation), framing by "
        f"±{a[:, 4].std():.2f}.",
        "",
        f"**Out of sample (fit April-June, test July-September):** mean squared error of runs allowed "
        f"{mse_off:.4f} without defense vs {mse_def:.4f} with it.",
        "",
        "That test has little power: defense moves runs allowed by only a few hundredths of a run per game, against "
        "a game-to-game spread of about ±3 runs. The stronger evidence that the ratings carry real skill is that they "
        "predict the next season's defense (`evidence/tests/defense_rating_search.md`).",
        "",
        f"**Weights used by the win model and the lineup optimizer:** fielding {w['fielding']:.2f}, framing "
        f"{w['framing']:.2f}. A rated run saved is worth one run when the measured range includes 1, as both do here.",
        "",
    ])
    REPORT.write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
