"""Which pre-game numbers best predict how a hitter does against today's starter? (no LLM, a few minutes)

Every 2026 start (hitter vs the opposing starter's hand that day). Candidate ways to value the plate appearance:
  hitter:  wOBA, xwOBA, or a 50/50 blend; regressed toward league at k = 50 / 100 / 200 / 400 / 800 PA
  platoon: the league-wide split, or the hitter's own split vs this hand (regressed toward the league split)
  starter: wOBA allowed, xwOBA allowed, or a blend; regressed at k = 100 / 200 / 400 / 800 batters faced
Each candidate gets a linear calibration fitted on April-June starts and is scored on July-September starts by
PA-weighted mean squared error against what actually happened. The winner is written to
data/lineup_params.json as the app's lineup value model; the full table goes to evidence/tests/value_model_search.md.
"""

from __future__ import annotations

import itertools
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
from backend.engine.pitching import pitcher_split  # noqa: E402

PARAMS = ROOT / "data" / "lineup_params.json"
REPORT = ROOT / "evidence" / "tests" / "value_model_search.md"
SPLIT = "2026-07-01"


@lru_cache(maxsize=None)
def hit(pid: int, d: str, hand: str | None) -> tuple[float | None, float | None, int]:
    r = batter_split(pid, d, hand, keys=["woba", "xwoba"])
    return r["woba"], r["xwoba"], r["sample"]["pa"]


@lru_cache(maxsize=None)
def pit(pid: int, d: str) -> tuple[float | None, float | None, int]:
    r = pitcher_split(pid, d)
    return r["woba"], r["xwoba"], r["sample"]["batters_faced"]


def shrink(v: float | None, n: float, k: float, to: float) -> float:
    return to if v is None else (v * n + to * k) / (n + k)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import win_model as wm
    wm.load_constants()
    adv, same = wm.platoon_split()
    LG, LGX = wm.LEAGUE, wm.LG_XWOBA
    rows = json.loads(wm.FEATURES.read_text(encoding="utf-8"))
    outcome = {(r["game_pk"], r["batter_id"], r["p_throws"]): (r["num"], r["den"]) for r in db.rows(
        "SELECT game_pk, batter_id, p_throws, SUM(woba_num) num, SUM(woba_den) den FROM statcast_batter_game GROUP BY 1, 2, 3")}
    recs = []
    for g in rows:
        d = g["date"]
        for side, other in (("home", "away"), ("away", "home")):
            sp = g[other]["sp"]
            hand = wm.hand(sp["pid"])[1] or "R"
            pw, px, pn = pit(sp["pid"], d)
            for e in g[side]["lineup"]:
                num, den = outcome.get((g["game_pk"], e["pid"], hand), (0, 0))
                if not den:
                    continue
                hw, hx, hn = hit(e["pid"], d, None)
                sw, sx, sn = hit(e["pid"], d, hand)
                recs.append((d < SPLIT, num / den, den, hw, hx, hn, sw, sx, sn, e["edge"], pw, px, pn))
    print(f"{len(recs):,} hitter-games")
    train = np.array([r[0] for r in recs])
    y = np.array([r[1] for r in recs]); w = np.array([r[2] for r in recs])

    def values(hm: str, kh: float, plat: str, pm: str, kp: float) -> np.ndarray:
        out = np.empty(len(recs))
        for i, r in enumerate(recs):
            _, _, _, hw, hx, hn, sw, sx, sn, edge, pw, px, pn = r
            hw_, hx_ = shrink(hw, hn, kh, LG), shrink(hx, hn, kh, LGX) - LGX + LG
            h = {"woba": hw_, "xwoba": hx_, "blend": (hw_ + hx_) / 2}[hm]
            lg_plat = adv if edge else same
            if plat == "league":
                pl = lg_plat
            else:   # his own split vs this hand, minus his overall, regressed toward the league split
                own = (sw - hw) if (sw is not None and hw is not None) else lg_plat
                pl = (own * sn + lg_plat * 400) / (sn + 400)
            pw_, px_ = shrink(pw, pn, kp, LG), shrink(px, pn, kp, LGX) - LGX + LG
            p = {"woba": pw_, "xwoba": px_, "blend": (pw_ + px_) / 2}[pm]
            out[i] = h + pl + p - LG
        return out

    results = []
    grid = itertools.product(("woba", "xwoba", "blend"), (50, 100, 200, 400, 800), ("league", "own"),
                             ("woba", "xwoba", "blend"), (100, 200, 400, 800))
    for hm, kh, plat, pm, kp in grid:
        v = values(hm, kh, plat, pm, kp)
        X = np.column_stack([np.ones(len(v)), v])
        W = np.sqrt(w[train])
        b = np.linalg.lstsq(X[train] * W[:, None], y[train] * W, rcond=None)[0]
        pred = X[~train] @ b
        mse = float(np.average((y[~train] - pred) ** 2, weights=w[~train]))
        results.append({"hitter": hm, "k_hitter": kh, "platoon": plat, "pitcher": pm, "k_pitcher": kp,
                        "test_mse": mse, "slope": float(b[1])})
    base_mse = float(np.average((y[~train] - np.average(y[train], weights=w[train])) ** 2, weights=w[~train]))
    results.sort(key=lambda r: r["test_mse"])
    best = results[0]
    current = next(r for r in results if (r["hitter"], r["k_hitter"], r["platoon"], r["pitcher"], r["k_pitcher"])
                   == ("woba", 200, "league", "woba", 400))
    params = json.loads(PARAMS.read_text(encoding="utf-8")) if PARAMS.exists() else {}
    params["value_model"] = {k: best[k] for k in ("hitter", "k_hitter", "platoon", "pitcher", "k_pitcher")}
    PARAMS.write_text(json.dumps(params, indent=2), encoding="utf-8")
    gain = lambda r: 100 * (1 - r["test_mse"] / base_mse)  # noqa: E731
    md = [
        "# Which pre-game numbers best predict a hitter against today's starter?",
        "",
        f"{len(recs):,} 2026 hitter-games. Each candidate is calibrated on April-June and scored on July-September "
        "(PA-weighted mean squared error vs how the hitter actually hit against that starter's hand). \"Signal\" is "
        "how much of the error a league-average guess leaves that the candidate removes. Single games are very noisy, "
        "so every candidate's share is small; what matters is the ranking. Script: `scripts/value_model_search.py`.",
        "",
        "| Rank | Hitter value | Regress hitter at | Platoon | Starter value | Regress starter at | Signal vs league average |",
        "|---|---|---|---|---|---|---|",
        *[f"| {i + 1} | {r['hitter']} | {r['k_hitter']} PA | {r['platoon']} | {r['pitcher']} | {r['k_pitcher']} BF | "
          f"{gain(r):.3f}% |" for i, r in enumerate(results[:10])],
        f"| ... | | | | | | |",
        f"| {results.index(current) + 1} (the win model used so far) | woba | 200 PA | league | woba | 400 BF | {gain(current):.3f}% |",
        f"| {len(results)} (worst) | {results[-1]['hitter']} | {results[-1]['k_hitter']} PA | {results[-1]['platoon']} | "
        f"{results[-1]['pitcher']} | {results[-1]['k_pitcher']} BF | {gain(results[-1]):.3f}% |",
        "",
        f"**Chosen for the app's lineup model:** hitter {best['hitter']} regressed at {best['k_hitter']} PA, "
        f"{best['platoon']} platoon split, starter {best['pitcher']} regressed at {best['k_pitcher']} batters faced. "
        f"It removes {gain(best) / gain(current):.2f}x as much error as the version used so far.",
        "",
    ]
    REPORT.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
