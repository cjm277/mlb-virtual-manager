"""Marcel-style projections: should a hitter (and a starter) be regressed toward his OWN 2025, not the league? (no LLM)

The lineup model so far (scripts/value_model_search.py) values a hitter by his stats in the app's fade blend: 2025
fades out over the first six weeks of 2026, and after that only 2026-to-date counts, regressed toward league average.
So a hitter with 150 PA in July is pulled halfway to average even when he had 600 strong PA in 2025.

Marcel (Tango's projection system) instead pools the seasons, each weighted, and regresses the pool toward league:
    value = (2026 counts + w25 x 2025 counts + k x league) / (2026 PA + w25 x 2025 PA + k)
The same for the starter's wOBA allowed, and for the hitter's own platoon split (his split vs this hand minus his
overall, both pooled the same way, regressed toward the league split at P plate appearances vs that hand).

Every 2026 hitter-start (43k), as in value_model_search.py: each candidate gets a linear calibration fitted on
April-June and is scored on July-September by PA-weighted mean squared error against how the hitter actually hit
against that starter's hand. The current app model (fade blend, xwOBA k=200, own platoon at 400 PA, starter wOBA
k=400) is scored on the same rows for comparison. The winner is written to data/lineup_params.json under
"projection"; the table goes to evidence/tests/projection_search.md.

Back seasons: 2025 (Statcast, with platoon splits) and 2024 (Savant expected stats, overall only;
scripts/fetch_history.py). Marcel's classic weights fall with age (5/4/3), so the 2024 weight is searched at or
below the 2025 weight. Platoon splits use 2026 and 2025 only.

Usage: python scripts/projection_search.py        (about a minute)
"""

from __future__ import annotations

import itertools
import json
import sys
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import db  # noqa: E402
from backend.engine.common import prior_weight  # noqa: E402

PARAMS = ROOT / "data" / "lineup_params.json"
REPORT = ROOT / "evidence" / "tests" / "projection_search.md"
SPLIT = "2026-07-01"
CURRENT = {"hitter": "xwoba", "k_hitter": 200, "platoon_pa": 400, "pitcher": "woba", "k_pitcher": 400}


class Counts:
    """Cumulative 2026 counts per player (optionally per hand), and 2025 season totals. Each count is a vector
    (wOBA numerator, xwOBA numerator, wOBA denominator)."""

    def __init__(self, game_sql: str, season_sql: str):
        rows = defaultdict(list)
        for r in db.rows(game_sql):
            rows[(r["id"], r["hand"])].append((r["d"], r["n"] or 0.0, r["x"] or 0.0, r["w"] or 0.0))
        self.cum = {}
        for key, v in rows.items():
            v.sort()
            dates = [a[0] for a in v]
            c = np.cumsum(np.array([a[1:] for a in v]), axis=0)
            self.cum[key] = (dates, c)
        self.prior = {(r["id"], r["hand"]): np.array([r["n"] or 0.0, r["x"] or 0.0, r["w"] or 0.0])
                      for r in db.rows(season_sql)}

    def before(self, pid: int, hand: str | None, d: str) -> np.ndarray:
        """2026 counts in games strictly before d (hand None = all)."""
        if hand is None:
            return self.before(pid, "L", d) + self.before(pid, "R", d)
        got = self.cum.get((pid, hand))
        if not got:
            return np.zeros(3)
        dates, c = got
        i = bisect_left(dates, d)
        return c[i - 1] if i else np.zeros(3)

    def season(self, pid: int, hand: str | None) -> np.ndarray:
        if hand is None:
            return self.season(pid, "L") + self.season(pid, "R")
        return self.prior.get((pid, hand), np.zeros(3))


def rate(c: np.ndarray, metric: str, lg: float, lgx: float) -> float | None:
    if c[2] <= 0:
        return None
    w, x = c[0] / c[2], c[1] / c[2] - lgx + lg
    return {"woba": w, "xwoba": x, "blend": (w + x) / 2}[metric]


def marcel(cur: np.ndarray, prior: np.ndarray, w25: float, k: float, metric: str, lg: float, lgx: float,
           c24: np.ndarray | None = None, w24: float = 0.0) -> float:
    pool = cur + w25 * prior + (w24 * c24 if c24 is not None else 0.0)
    n = pool[2]
    r = rate(pool, metric, lg, lgx)
    return lg if r is None else (r * n + lg * k) / (n + k)


def fade(cur: np.ndarray, prior: np.ndarray, d: str, k: float, metric: str, lg: float, lgx: float) -> float:
    """The app's current blend: rates mixed with the 2025 fade weight, then regressed toward league."""
    w = prior_weight(d)
    a, b = rate(cur, metric, lg, lgx), rate(prior, metric, lg, lgx)
    if b is None:
        w = 0.0
    elif a is None:
        w = 1.0
    r = b if w == 1 else a if w == 0 else (1 - w) * a + w * b
    n = (1 - w) * cur[2] + w * prior[2]
    return lg if r is None else (r * n + lg * k) / (n + k)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import win_model as wm
    wm.load_constants()
    adv, same = wm.platoon_split()
    LG, LGX = wm.LEAGUE, wm.LG_XWOBA
    bat = Counts("SELECT batter_id id, p_throws hand, game_date d, SUM(woba_num) n, SUM(xwoba_num) x, SUM(woba_den) w "
                 "FROM statcast_batter_game GROUP BY 1, 2, 3",
                 "SELECT batter_id id, p_throws hand, SUM(woba_num) n, SUM(xwoba_num) x, SUM(woba_den) w "
                 "FROM statcast_batter_season WHERE season = 2025 GROUP BY 1, 2")
    pit = Counts("SELECT pitcher_id id, stand hand, game_date d, SUM(woba_num) n, SUM(xwoba_num) x, SUM(woba_den) w "
                 "FROM statcast_pitcher_game GROUP BY 1, 2, 3",
                 "SELECT pitcher_id id, stand hand, SUM(woba_num) n, SUM(xwoba_num) x, SUM(woba_den) w "
                 "FROM statcast_pitcher_season WHERE season = 2025 GROUP BY 1, 2")
    old = {(r["player_id"], r["role"]): np.array([(r["woba"] or 0.0) * r["pa"], (r["xwoba"] or 0.0) * r["pa"], r["pa"]])
           for r in db.rows("SELECT * FROM expected_stats_history WHERE season = 2024")}
    zero = np.zeros(3)
    games = json.loads(wm.FEATURES.read_text(encoding="utf-8"))
    outcome = {(r["game_pk"], r["batter_id"], r["p_throws"]): (r["num"], r["den"]) for r in db.rows(
        "SELECT game_pk, batter_id, p_throws, SUM(woba_num) num, SUM(woba_den) den FROM statcast_batter_game GROUP BY 1, 2, 3")}
    recs = []
    for g in games:
        d = g["date"]
        for side, other in (("home", "away"), ("away", "home")):
            sp = g[other]["sp"]["pid"]
            hand = wm.hand(sp)[1] or "R"
            for e in g[side]["lineup"]:
                num, den = outcome.get((g["game_pk"], e["pid"], hand), (0, 0))
                if den:
                    recs.append({"d": d, "y": num / den, "w": den, "edge": e["edge"],
                                 "h26": bat.before(e["pid"], None, d), "h25": bat.season(e["pid"], None),
                                 "s26": bat.before(e["pid"], hand, d), "s25": bat.season(e["pid"], hand),
                                 "p26": pit.before(sp, None, d), "p25": pit.season(sp, None),
                                 "h24": old.get((e["pid"], "batter"), zero), "p24": old.get((sp, "pitcher"), zero)})
    print(f"{len(recs):,} hitter-games", flush=True)
    train = np.array([r["d"] < SPLIT for r in recs])
    y = np.array([r["y"] for r in recs]); w = np.array([r["w"] for r in recs])
    lg_plat = np.array([adv if r["edge"] else same for r in recs])

    def hitter_vec(metric, w25, k, how="marcel", w24=0.0):
        if how == "fade":
            return np.array([fade(r["h26"], r["h25"], r["d"], k, metric, LG, LGX) for r in recs])
        return np.array([marcel(r["h26"], r["h25"], w25, k, metric, LG, LGX, r["h24"], w24) for r in recs])

    def pitcher_vec(metric, w25, k, how="marcel", w24=0.0):
        if how == "fade":
            return np.array([fade(r["p26"], r["p25"], r["d"], k, metric, LG, LGX) for r in recs])
        return np.array([marcel(r["p26"], r["p25"], w25, k, metric, LG, LGX, r["p24"], w24) for r in recs])

    def platoon_vec(w25, P, how="marcel"):
        out = np.empty(len(recs))
        for i, r in enumerate(recs):
            if P is None:
                out[i] = lg_plat[i]
                continue
            if how == "fade":
                wt = prior_weight(r["d"])
                a_s, b_s = rate(r["s26"], "woba", LG, LGX), rate(r["s25"], "woba", LG, LGX)
                a_o, b_o = rate(r["h26"], "woba", LG, LGX), rate(r["h25"], "woba", LG, LGX)
                mix = lambda a, b, t: (b if a is None else a if b is None else (1 - t) * a + t * b)  # noqa: E731
                sp_, ov = mix(a_s, b_s, wt), mix(a_o, b_o, wt)
                if b_s is None:
                    wt = 0.0
                elif a_s is None:
                    wt = 1.0
                n = (1 - wt) * r["s26"][2] + wt * r["s25"][2]
            else:
                sp_ = rate(r["s26"] + w25 * r["s25"], "woba", LG, LGX)
                ov = rate(r["h26"] + w25 * r["h25"], "woba", LG, LGX)
                n = (r["s26"] + w25 * r["s25"])[2]
            own = (sp_ - ov) if (sp_ is not None and ov is not None) else lg_plat[i]
            out[i] = (own * n + lg_plat[i] * P) / (n + P)
        return out

    def score(v: np.ndarray) -> tuple[float, float]:
        X = np.column_stack([np.ones(len(v)), v])
        W = np.sqrt(w[train])
        b = np.linalg.lstsq(X[train] * W[:, None], y[train] * W, rcond=None)[0]
        pred = X[~train] @ b
        return float(np.average((y[~train] - pred) ** 2, weights=w[~train])), float(b[1])

    base_mse = float(np.average((y[~train] - np.average(y[train], weights=w[train])) ** 2, weights=w[~train]))
    gain = lambda mse: 100 * (1 - mse / base_mse)  # noqa: E731

    # The three parts add (hitter + platoon + starter - league), so each part's vectors are computed once.
    W25 = (0.0, 0.25, 0.5, 0.75, 1.0)
    W24 = (0.0, 0.25, 0.5, 0.75)
    H = {(m, a, b, k): hitter_vec(m, a, k, w24=b) for m in ("woba", "xwoba", "blend") for a in W25 for b in W24 if b <= a
         for k in (50, 100, 200, 400, 800)}
    PL = {(a, P): platoon_vec(a, P) for a in W25 for P in (50, 100, 200, 400, 800, 1600, 3200)} | {(0.0, None): lg_plat}
    PI = {(m, a, b, k): pitcher_vec(m, a, k, w24=b) for m in ("woba", "xwoba", "blend") for a in W25 for b in W24 if b <= a
          for k in (100, 200, 400, 800, 1600)}
    print(f"{len(H)} hitter x {len(PL)} platoon x {len(PI)} starter candidates", flush=True)

    # Stage 1: best hitter projection with the current platoon and starter parts; stage 2: platoon; stage 3: starter.
    cur_pl = platoon_vec(0.0, 400, "fade")
    cur_pi = pitcher_vec("woba", 0.0, 400, "fade")
    cur_h = hitter_vec("xwoba", 0.0, 200, "fade")
    current = score(cur_h + cur_pl + cur_pi - LG)
    hs = sorted(((score(v + cur_pl + cur_pi - LG), key) for key, v in H.items()), key=lambda t: t[0][0])
    bh = hs[0][1]
    pls = sorted(((score(H[bh] + v + cur_pi - LG), key) for key, v in PL.items()), key=lambda t: t[0][0])
    bp = pls[0][1]
    pis = sorted(((score(H[bh] + PL[bp] + v - LG), key) for key, v in PI.items()), key=lambda t: t[0][0])
    bs = pis[0][1]
    # One more pass over the hitter part with the chosen platoon and starter parts (they interact a little).
    hs2 = sorted(((score(v + PL[bp] + PI[bs] - LG), key) for key, v in H.items()), key=lambda t: t[0][0])
    bh = hs2[0][1]
    # An extra back season must earn its place: keep 2024 only if it adds at least 0.01 points of hold-out signal.
    for which in ("hitter", "pitcher"):
        key = bh if which == "hitter" else bs
        no24 = (key[0], key[1], 0.0, key[3])
        with24 = score(H[bh] + PL[bp] + PI[bs] - LG)
        alt = score((H[no24] if which == "hitter" else H[bh]) + PL[bp] + (PI[no24] if which == "pitcher" else PI[bs]) - LG)
        if gain(with24[0]) - gain(alt[0]) < 0.01:
            bh, bs = (no24, bs) if which == "hitter" else (bh, no24)
    best = score(H[bh] + PL[bp] + PI[bs] - LG)

    choice = {"hitter": bh[0], "w2025_hitter": bh[1], "w2024_hitter": bh[2], "k_hitter": bh[3], "platoon_w2025": bp[0],
              "platoon_pa": bp[1], "pitcher": bs[0], "w2025_pitcher": bs[1], "w2024_pitcher": bs[2], "k_pitcher": bs[3],
              "holdout_signal_pct": gain(best[0]), "current_signal_pct": gain(current[0]),
              "calibration_slope": best[1], "current_calibration_slope": current[1]}
    params = json.loads(PARAMS.read_text(encoding="utf-8"))
    params["projection"] = choice
    PARAMS.write_text(json.dumps(params, indent=2), encoding="utf-8")

    def row(label, sc):
        return f"| {label} | {gain(sc[0]):.3f}% | {sc[1]:.2f} |"

    lookup_h = {k: s for s, k in hs2}
    lookup_p = {k: s for s, k in pls}
    lookup_s = {k: s for s, k in pis}
    md = [
        "# Marcel-style projections: regress toward the player's own track record (2025, 2024), not only the league",
        "",
        f"{len(recs):,} 2026 hitter-starts. Calibrated on April-June, scored on the July-September hold-out (PA-weighted "
        "mean squared error vs how each hitter actually hit against that starter's hand). \"Signal\" = share of a "
        "league-average guess's error that the candidate removes; single games are very noisy, so shares are small and "
        "the ranking is what matters. \"Calibration slope\" = how much of a rated difference shows up in the hold-out "
        "(1 = fully). Script: `scripts/projection_search.py`.",
        "",
        "Marcel pools the seasons, `(2026 + w x 2025) counts`, then regresses the pool toward league at k plate "
        "appearances. The app's model so far used the fade blend: 2025 fades out over the first six weeks, then only "
        "2026-to-date counts.",
        "",
        "## Result",
        "",
        "| Model | Signal on Jul-Sep hold-out | Calibration slope |",
        "|---|---|---|",
        row("Current app model (fade blend; hitter xwOBA k=200; own platoon at 400 PA; starter wOBA k=400)", current),
        row(f"**Chosen: Marcel** (hitter {bh[0]}, 2025 weight {bh[1]}, 2024 weight {bh[2]}, k={bh[3]}; own platoon, "
            f"2025 weight {bp[0]}, regressed at {bp[1]} PA; starter {bs[0]}, 2025 weight {bs[1]}, 2024 weight {bs[2]}, "
            f"k={bs[3]})", best),
        row("Same, with 2024 added for hitters at its best weight (0.25); rejected, adds under 0.01 points",
            score(H[(bh[0], bh[1], 0.25, bh[3])] + PL[bp] + PI[bs] - LG)),
        "",
        f"The chosen model removes **{gain(best[0]) / gain(current[0]):.2f}x** as much hold-out error as the current one.",
        "",
        "## Hitter part (platoon and starter parts as chosen)",
        "",
        "| Hitter value | 2025 weight | 2024 weight | Regress at (PA) | Signal | Slope |",
        "|---|---|---|---|---|---|",
        *[f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {gain(s[0]):.3f}% | {s[1]:.2f} |" for s, k in hs2[:8]],
        "",
        "Same metric, 2025 weight and k as chosen, by 2024 weight:",
        "",
        "| 2024 weight | Signal | Slope |",
        "|---|---|---|",
        *[f"| {b} | {gain(lookup_h[(bh[0], bh[1], b, bh[3])][0]):.3f}% | {lookup_h[(bh[0], bh[1], b, bh[3])][1]:.2f} |"
          for b in W24 if b <= bh[1]],
        "",
        "## Platoon part: how hard to regress a hitter's own split",
        "",
        "| 2025 weight | Regress at (PA vs that hand) | Signal | Slope |",
        "|---|---|---|---|",
        *[f"| {k[0]} | {'league split only' if k[1] is None else k[1]} | {gain(s[0]):.3f}% | {s[1]:.2f} |"
          for s, k in pls[:8]],
        f"| 0.0 | league split only | {gain(lookup_p[(0.0, None)][0]):.3f}% | {lookup_p[(0.0, None)][1]:.2f} |",
        "",
        "## Starter part",
        "",
        "| Starter value | 2025 weight | 2024 weight | Regress at (BF) | Signal | Slope |",
        "|---|---|---|---|---|---|",
        *[f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {gain(s[0]):.3f}% | {s[1]:.2f} |" for s, k in pis[:8]],
        "",
        "Same metric, 2025 weight and k as chosen, by 2024 weight:",
        "",
        "| 2024 weight | Signal | Slope |",
        "|---|---|---|",
        *[f"| {b} | {gain(lookup_s[(bs[0], bs[1], b, bs[3])][0]):.3f}% | {lookup_s[(bs[0], bs[1], b, bs[3])][1]:.2f} |"
          for b in W24 if b <= bs[1]],
        "",
    ]
    REPORT.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
