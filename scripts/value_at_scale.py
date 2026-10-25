"""The lineup insight scored on EVERY 2026 team-game, before and after the Marcel projection and catcher cap (no LLM).

The verified value so far (evidence/tests/value_verification.md) rests on 150 sampled plans. Its floor was low
because the direct check on those plans (what the players did after the game) was too noisy to confirm fielding.
The lineup is now built by code (backend/engine/winmodel.best_lineup), so it can be rebuilt for all 4,858 2026
team-games at no model cost:

  before  the app's lineup model up to now (fade projection, no catcher cap)
  marcel  + Marcel projection (2026 pooled with 2025, own platoon split; scripts/projection_search.py)
  after   + catcher workload cap (at most 7 of the team's last 10 games behind the plate), with each team's season
          replayed in date order so the cap counts the catchers WE chose, not the ones the real manager chose

Each lineup is built against the PREDICTED opposing starter (the app stays predictive), from the active roster that
day. Our starter is the real one (lineup insight only; the starter-choice piece is unchanged and added separately).
Then every version is scored against the real manager's lineup exactly as in value_verification.py:

  - verified: each piece valued by what held-out data says it is worth. Offense through the best calibrated
    projection we have (Marcel, times its rest-of-season calibration slope; the older season-stats lens is shown too),
    fielding by the 2026 calibration by how established the fielder is at the position, framing by its 2026 slope,
    cut for catcher workload only where the plan exceeds a real workload.
  - direct check: the same lineups scored on what every player did AFTER the game (rest-of-2026 wOBA, 2026 fielding
    and framing). No pre-game number enters it, so it can't be flattered by the optimizer.

Usage: python scripts/value_at_scale.py build     (rebuilds every lineup, about 5 minutes on 8 processes)
       python scripts/value_at_scale.py score     (scores the saved lineups and writes the report)
       python scripts/value_at_scale.py           (both)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict, deque
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import db  # noqa: E402

SAVE = ROOT / "evidence" / "logs" / "value_at_scale"
LINEUPS = SAVE / "lineups.json"
RESULTS = SAVE / "results.json"
REPORT = ROOT / "evidence" / "tests" / "value_at_scale.md"
NOTES = ROOT / "evidence" / "tests" / "value_at_scale_interpretation.md"     # hand-written; appended if present
VERSIONS = {"before": ("fade", False), "marcel": ("marcel", False), "after": ("marcel", True)}
LABELS = {"before": "Before (app model up to now)", "marcel": "+ Marcel projection",
          "after": "+ Marcel + catcher cap (now in the app)"}
SEED = 409
BOOT = 2000
HOLDOUT = "2026-07-01"


# ---------------------------------------------------------------------------
# Stage 1: build every lineup
# ---------------------------------------------------------------------------

def team_games(team_id: int) -> list[dict]:
    """Every 2026 game the team played, in order (doubleheaders by game number)."""
    return [dict(r) for r in db.rows(
        """SELECT game_pk, game_date d, game_number gn, home_team_id h, away_team_id a FROM games
           WHERE home_team_id = ? OR away_team_id = ? ORDER BY game_date, game_number""", team_id, team_id)]


def build_team(team_id: int) -> list[dict]:
    from backend.engine import rotation, winmodel
    games = team_games(team_id)
    out = {g["game_pk"]: {"game_pk": g["game_pk"], "team_id": team_id, "date": g["d"], "home": g["h"] == team_id,
                          "lineups": {}} for g in games}
    preds = {}
    for g in games:
        opp = g["a"] if g["h"] == team_id else g["h"]
        try:
            p = rotation.predict_starter(opp, g["d"], g["gn"] or 1)["predicted"]
            preds[g["game_pk"]] = p["player_id"] if p else None
        except Exception:                       # noqa: BLE001 - a game the predictor can't handle is skipped
            preds[g["game_pk"]] = None
        out[g["game_pk"]]["pred_sp"] = preds[g["game_pk"]]
    for v, (proj, cap) in VERSIONS.items():
        winmodel.set_version(proj)
        mine: deque = deque(maxlen=winmodel.CATCHER_WINDOW)      # the catchers this version chose, most recent last
        for g in games:
            sp = preds[g["game_pk"]]
            if not sp:
                continue
            recent = dict(zip(*np.unique(list(mine), return_counts=True))) if mine else {}
            recent = {int(k): int(n) for k, n in recent.items()}
            try:
                ml = winmodel.best_lineup(team_id, g["d"], sp, home=g["h"] == team_id, catcher_cap=cap,
                                          catcher_recent=recent if cap else None)
            except ValueError:
                continue
            out[g["game_pk"]]["lineups"][v] = [[x["slot"], x["player_id"], x["position"]] for x in ml["lineup"]]
            mine.append(next(x["player_id"] for x in ml["lineup"] if x["position"] == "C"))
    return list(out.values())


def build() -> None:
    SAVE.mkdir(parents=True, exist_ok=True)
    teams = [r["team_id"] for r in db.rows("SELECT team_id FROM teams ORDER BY team_id")]
    rows = []
    with Pool(8) as pool:
        for i, part in enumerate(pool.imap_unordered(build_team, teams), 1):
            rows += part
            print(f"  {i}/{len(teams)} teams", flush=True)
    LINEUPS.write_text(json.dumps(rows), encoding="utf-8")
    print(f"saved {len(rows)} team-games", flush=True)


# ---------------------------------------------------------------------------
# Stage 2: score
# ---------------------------------------------------------------------------

def score() -> dict:
    sys.stdout.reconfigure(encoding="utf-8")
    import value_verification as vv
    import win_model as wm
    from backend.engine import defense as dfn
    from backend.engine import roster
    from backend.engine import winmodel
    wm.load_constants()
    rng = np.random.default_rng(SEED)
    feats = {g["game_pk"]: g for g in json.loads(wm.FEATURES.read_text(encoding="utf-8"))}
    built = json.loads(LINEUPS.read_text(encoding="utf-8"))

    def entry(pid: int, slot: int, d: str, opp_sp: int) -> dict:
        w, n = wm.hitter(pid, d)
        bats = wm.hand(pid)[0]
        throws = wm.hand(opp_sp)[1] or "R"
        from backend.engine.matchups import batting_side
        return {"pid": pid, "slot": slot, "woba": w, "n": n, "edge": batting_side(bats, throws) != throws}

    cases = []
    for b in built:
        g = feats.get(b["game_pk"])
        if not g or not all(v in b["lineups"] for v in VERSIONS):
            continue
        us = "home" if b["home"] else "away"
        them = "away" if b["home"] else "home"
        opp_id = g[them + "_id"]
        d = g["date"]
        base = {"gpk": b["game_pk"], "team_id": b["team_id"], "date": d, "home": b["home"],
                "real": {"lineup": g[us]["lineup"], "sp": g[us]["sp"]}, "opp_real": g[them]["lineup"],
                "opp_vs_plan_sp": g[them]["lineup"], "opp_sp": g[them]["sp"],
                "opp_pos": wm.real_positions(b["game_pk"], opp_id), "real_pos": wm.real_positions(b["game_pk"], b["team_id"]),
                "pred_right": b["pred_sp"] == g[them]["sp"]["pid"]}
        if len(base["real_pos"]) != 9 or len(base["opp_pos"]) != 9 or len(g[us]["lineup"]) != 9:
            continue
        per = {}
        for v in VERSIONS:
            lu = b["lineups"][v]
            per[v] = dict(base, plan={"lineup": [entry(p, s, d, g[them]["sp"]["pid"]) for s, p, _ in lu], "sp": g[us]["sp"]},
                          plan_pos={p: pos for _, p, pos in lu})
        cases.append(per)
    n = len(cases)
    print(f"{n} team-games scored", flush=True)

    # Lenses
    S = {"hitter": vv.season_hitter, "pitcher": vv.season_pitcher, "defense": vv.season_defense}
    winmodel.set_version("marcel")

    @lru_cache(maxsize=None)
    def marcel_value(pid: int, d: str) -> float:
        return winmodel.hitter_value(pid, d)

    M = dict(S, hitter=lambda e, d: marcel_value(e["pid"], d))
    F = vv.Future(100, 200)
    FL = {"hitter": F.hitter, "pitcher": F.pitcher, "defense": F.defense}

    # Calibration of each offense lens: rest-of-2026 wOBA on the pre-game value, every 2026 start, by player.
    fut0 = vv.Future(0, 0)
    xs = defaultdict(list)
    for g in feats.values():
        for side in ("home", "away"):
            for e in g[side]["lineup"]:
                num, w = fut0._after(fut0.bat, e["pid"], g["date"])
                if w >= 30:
                    xs["pid"].append(e["pid"]); xs["y"].append(num / w); xs["w"].append(w)
                    xs["S"].append(vv.season_hitter(e, g["date"])); xs["M"].append(marcel_value(e["pid"], g["date"]))
                    xs["late"].append(g["date"] >= HOLDOUT)
    y, w, late = np.array(xs["y"]), np.array(xs["w"]), np.array(xs["late"])
    rows_of = defaultdict(list)
    for i, p in enumerate(xs["pid"]):
        rows_of[p].append(i)
    players = list(rows_of)

    def slope(x, idx):
        A = np.column_stack([np.ones(len(idx)), x[idx]])
        return float(np.linalg.solve(A.T @ (A * w[idx][:, None]), A.T @ (w[idx] * y[idx]))[1])

    calib = {}
    for name in ("S", "M"):
        x = np.array(xs[name])
        draws = [slope(x, np.array([i for k in rng.integers(0, len(players), len(players)) for i in rows_of[players[k]]]))
                 for _ in range(300)]
        calib[name] = {"slope": slope(x, np.arange(len(x))), "ci": np.percentile(draws, [2.5, 97.5]).tolist(),
                       "draws": draws, "slope_jul_sep": slope(x, np.flatnonzero(late))}
    print("calibration", {k: round(v["slope"], 3) for k, v in calib.items()}, flush=True)

    rel = vv.defense_reliability(rng)
    cal = vv.defense_calibration(rng)
    B = vv.BUCKETS

    # Per-version, per-game ingredients
    ing = {}
    for v in VERSIONS:
        cs = [c[v] for c in cases]
        offS = vv.split_lineup(cs, S)["offense"]
        offM = vv.split_lineup(cs, M)["offense"]
        T = [vv.defense_terms(c) for c in cs]
        indep = vv.split_lineup(cs, FL)
        seasonlens = vv.edges(cs, S)["lineup"]
        ing[v] = {"offS": offS, "offM": offM, "cnt": np.array([t["count"] for t in T]),
                  "rat": np.array([t["rating"] for t in T]), "frm": np.array([t["framing"] for t in T]),
                  "ind_off": indep["offense"], "ind_def": indep["defense"], "season": seasonlens}
        print(f"  {v} scored", flush=True)
    k = np.array([vv.wp_per_run_allowed(c["before"], S) for c in cases])

    # Catcher workload in each version: share of team-games caught by the team's best framer, and the busiest
    # catcher's share of his team's games.
    def catcher_use(v: str) -> dict:
        best_share, busiest = [], defaultdict(lambda: defaultdict(int))
        games_of = defaultdict(int)
        for c in cases:
            x = c[v]
            cs_ = [r["player_id"] for r in roster.active_roster(x["team_id"], x["date"]) if r["position"] == "C"]
            catcher = next(p for p, pos in x["plan_pos"].items() if pos == "C")
            busiest[x["team_id"]][catcher] += 1
            games_of[x["team_id"]] += 1
            if len(cs_) >= 2:
                best_share.append(catcher == max(cs_, key=lambda p: dfn.framing_per_game(p, 2025)))
        top = [max(cnt.values()) / games_of[t] for t, cnt in busiest.items()]
        return {"best_framer": float(np.mean(best_share)), "busiest_max": float(max(top)),
                "busiest_median": float(np.median(top))}

    real_c = vv.catcher_usage([dict(c["before"], plan=c["before"]["real"], plan_pos=c["before"]["real_pos"])
                               for c in cases[::5]])
    usage = {v: catcher_use(v) for v in VERSIONS}
    print("catchers", usage, flush=True)
    # Framing-gain cut: only where a version's busiest catcher exceeds what real catchers sustained (75% max)
    workload = {v: (1.0, 1.0, 1.0) if usage[v]["busiest_max"] <= 0.75 else vv.CATCHER_WORKLOAD for v in VERSIONS}

    a0 = np.array([cal[b]["intercept"] for b in B]); s0 = np.array([cal[b]["slope"] for b in B])
    fs0 = rel["framing"]["slope"]

    def parts(v, idx, hs, a, s, fs, wf, lens="M"):
        p = ing[v]
        fielding = k[idx] * ((p["cnt"][idx] * a).sum(1) + (p["rat"][idx] * s).sum(1))
        framing = k[idx] * fs * wf * p["frm"][idx]
        off = hs * p["off" + lens][idx]
        return {"offense": off, "fielding": fielding, "framing": framing}

    def summarize(v, mask=None, lens="M"):
        m = np.ones(n, bool) if mask is None else mask
        idx_all = np.flatnonzero(m)
        pt = parts(v, idx_all, calib[lens]["slope"], a0, s0, fs0, workload[v][1], lens)
        point = {q: float(162 * x.mean()) for q, x in pt.items()}
        sims = defaultdict(list)
        for _ in range(BOOT):
            j = rng.integers(0, 1000)
            a = np.array([cal[b]["draws"][j][0] for b in B]); s = np.array([cal[b]["draws"][j][1] for b in B])
            idx = rng.choice(idx_all, len(idx_all))
            got = parts(v, idx, rng.choice(calib[lens]["draws"]), a, s, rng.uniform(*rel["framing"]["ci"]),
                        rng.uniform(workload[v][0], workload[v][2]), lens)
            tot = 0.0
            for q, x in got.items():
                sims[q].append(162 * float(x.mean())); tot += 162 * float(x.mean())
            sims["total"].append(tot)
        point["total"] = sum(point.values())
        ci = {q: np.percentile(x, [2.5, 97.5]).tolist() for q, x in sims.items()}
        return {"point": point, "ci": ci}

    def direct(v, mask=None):
        m = np.ones(n, bool) if mask is None else mask
        o, dd = ing[v]["ind_off"][m], ing[v]["ind_def"][m]
        return {"offense": [162 * o.mean(), *[162 * x for x in vv.boot(o, rng)]],
                "defense": [162 * dd.mean(), *[162 * x for x in vv.boot(dd, rng)]],
                "total": [162 * (o + dd).mean(), *[162 * x for x in vv.boot(o + dd, rng)]]}

    def paired(a, b, key):
        x = ing[a][key] - ing[b][key]
        return [162 * x.mean(), *[162 * y for y in vv.boot(x, rng)]]

    v3 = {(int(c["run"].split("_g")[1].split("_")[0]), c["team_id"]) for c in vv.load_cases("v3")}
    in150 = np.array([(c["before"]["gpk"], c["before"]["team_id"]) in v3 for c in cases])
    late_m = np.array([c["before"]["date"] >= HOLDOUT for c in cases])
    right = np.array([c["before"]["pred_right"] for c in cases])
    # Players the model started who didn't appear that day or in the team's next game may have been hurt (the real
    # manager knew; the active roster didn't say). Sensitivity: drop those games.
    hurt = np.zeros(n, bool)
    appeared = defaultdict(set)
    for r in db.rows("SELECT team_id, game_date, player_id FROM batting_lines"):
        appeared[(r["team_id"], r["game_date"])].add(r["player_id"])
    dates_of = defaultdict(list)
    for (t, d) in appeared:
        dates_of[t].append(d)
    for t in dates_of:
        dates_of[t].sort()
    for i, c in enumerate(cases):
        x = c["after"]
        ds = dates_of[x["team_id"]]
        j = ds.index(x["date"]) if x["date"] in ds else None
        seen = appeared[(x["team_id"], x["date"])] | (appeared[(x["team_id"], ds[j + 1])] if j is not None and j + 1 < len(ds) else set())
        hurt[i] = any(e["pid"] not in seen for e in x["plan"]["lineup"])

    saved = json.loads(vv.OUT_JSON.read_text(encoding="utf-8"))
    out = {
        "n": n, "n_150": int(in150.sum()), "pred_right": float(right.mean()), "maybe_hurt_share": float(hurt.mean()),
        "calibration": {q: {a: b for a, b in v.items() if a != "draws"} for q, v in calib.items()},
        "catchers": usage, "catchers_real_sample": real_c, "workload": {v: list(x) for v, x in workload.items()},
        "verified": {v: summarize(v) for v in VERSIONS},
        "verified_season_lens": {v: summarize(v, lens="S") for v in VERSIONS},
        "verified_jul_sep": {v: summarize(v, late_m) for v in VERSIONS},
        "verified_150": {v: summarize(v, in150) for v in VERSIONS},
        "verified_no_maybe_hurt": {v: summarize(v, ~hurt) for v in VERSIONS},
        "direct": {v: direct(v) for v in VERSIONS},
        "direct_jul_sep": {v: direct(v, late_m) for v in VERSIONS},
        "direct_150": {v: direct(v, in150) for v in VERSIONS},
        "season_lens": {v: [162 * ing[v]["season"].mean(), *[162 * x for x in vv.boot(ing[v]["season"], rng)]]
                        for v in VERSIONS},
        "paired_direct": {"marcel_vs_before": {"offense": paired("marcel", "before", "ind_off"),
                                               "defense": paired("marcel", "before", "ind_def")},
                          "after_vs_marcel": {"offense": paired("after", "marcel", "ind_off"),
                                              "defense": paired("after", "marcel", "ind_def")}},
        "starter_extra": 162 * saved["verified"]["parts"]["starter"],
        "old_150_lineup": saved.get("lineup_valuation", {}).get("wins"),
    }
    RESULTS.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def f(x: float) -> str:
    return f"{x:+.2f}"


def rng_(v: list[float]) -> str:
    return f"{f(v[0])} ({f(v[1])} to {f(v[2])})"


def render(o: dict) -> str:
    V = o["verified"]
    A, Bf = V["after"], V["before"]
    D = o["direct"]
    total_after = A["point"]["total"] + o["starter_extra"]
    old = o.get("old_150_lineup") or {}
    L = [
        "# The lineup insight on every 2026 game: Marcel projection and catcher cap",
        "",
        "Generated by `scripts/value_at_scale.py` (no LLM calls, $0). Lineups: `evidence/logs/value_at_scale/lineups.json`; "
        "numbers: `results.json`. Wins are per 162 games against what the real manager did.",
        "",
        f"**Sample:** {o['n']:,} team-games, every 2026 game with a full real lineup on both sides (the earlier verification "
        f"used 150). Each lineup was built by code against the *predicted* opposing starter (right in {o['pred_right']:.0%} "
        "of games), from that day's active roster. Our starter is the real one: this is the lineup insight only (who plays, "
        "where, and in what order).",
        "",
        "## Headline",
        "",
        "| Version | Offense | Fielding | Framing | **Lineup insight, verified** |",
        "|---|---|---|---|---|",
        *[f"| {LABELS[v]} | {f(V[v]['point']['offense'])} | {f(V[v]['point']['fielding'])} | {f(V[v]['point']['framing'])} | "
          f"**{f(V[v]['point']['total'])}** ({f(V[v]['ci']['total'][0])} to {f(V[v]['ci']['total'][1])}) |" for v in VERSIONS],
        "",
        f"For comparison, the 150-plan valuation of the lineup insight was **{f(old['lineup'][0]) if old else '+1.15'}** "
        f"({f(old['lineup'][1]) if old else '+0.86'} to {f(old['lineup'][2]) if old else '+1.54'}). The same before-model "
        f"on just those 150 games here: {f(o['verified_150']['before']['point']['total'])}.",
        "",
        f"**Adding the starter-choice piece unchanged ({f(o['starter_extra'])}, from the 150-plan verification), the app "
        f"is now worth about {f(total_after)} wins per 162** on the verified estimate.",
        "",
        "## The direct check: what the players did after the game",
        "",
        "The same lineups scored only on rest-of-2026 results (hitters' wOBA, regressed at 100 PA; 2026 fielding and "
        "framing). No pre-game number enters it. On 150 plans it was too noisy to confirm anything; here it has 30x the games.",
        "",
        "| Version | Offense | Defense | Total |",
        "|---|---|---|---|",
        *[f"| {LABELS[v]} | {rng_(D[v]['offense'])} | {rng_(D[v]['defense'])} | {rng_(D[v]['total'])} |" for v in VERSIONS],
        "",
        "July-September only (the hold-out the projection was scored on):",
        "",
        "| Version | Offense | Defense | Total |",
        "|---|---|---|---|",
        *[f"| {LABELS[v]} | {rng_(o['direct_jul_sep'][v]['offense'])} | {rng_(o['direct_jul_sep'][v]['defense'])} | "
          f"{rng_(o['direct_jul_sep'][v]['total'])} |" for v in VERSIONS],
        "",
        "Paired changes on the same games (direct check):",
        "",
        "| Change | Offense | Defense |",
        "|---|---|---|",
        f"| Marcel projection (marcel minus before) | {rng_(o['paired_direct']['marcel_vs_before']['offense'])} | "
        f"{rng_(o['paired_direct']['marcel_vs_before']['defense'])} |",
        f"| Catcher cap (after minus marcel) | {rng_(o['paired_direct']['after_vs_marcel']['offense'])} | "
        f"{rng_(o['paired_direct']['after_vs_marcel']['defense'])} |",
        "",
        "## Robustness",
        "",
        "| Version | Verified, all games | Jul-Sep only | Older season-stats offense lens | Without games where a starter may have been hurt |",
        "|---|---|---|---|---|",
        *[f"| {LABELS[v]} | {f(V[v]['point']['total'])} | {f(o['verified_jul_sep'][v]['point']['total'])} | "
          f"{f(o['verified_season_lens'][v]['point']['total'])} | {f(o['verified_no_maybe_hurt'][v]['point']['total'])} |"
          for v in VERSIONS],
        "",
        f"- **May have been hurt:** in {o['maybe_hurt_share']:.0%} of games the model started someone who didn't appear "
        "that day or in the team's next game. The real manager may have known something the active roster didn't say.",
        f"- **Offense calibration** (rest-of-2026 wOBA on the pre-game value, every 2026 start): Marcel "
        f"{o['calibration']['M']['slope']:.2f} ({o['calibration']['M']['ci'][0]:.2f} to {o['calibration']['M']['ci'][1]:.2f}), "
        f"July-September starts {o['calibration']['M']['slope_jul_sep']:.2f}; the older season-stats value "
        f"{o['calibration']['S']['slope']:.2f}. A higher slope means more of a rated difference comes true.",
        "",
        "## Catcher workload",
        "",
        "| Version | Best framer catches | Busiest catcher's share of his team's games (max / median) | Framing gain kept |",
        "|---|---|---|---|",
        *[f"| {LABELS[v]} | {o['catchers'][v]['best_framer']:.0%} | {o['catchers'][v]['busiest_max']:.0%} / "
          f"{o['catchers'][v]['busiest_median']:.0%} | {o['workload'][v][0]:.0%}-{o['workload'][v][2]:.0%} |" for v in VERSIONS],
        f"| Real managers (sample of games) | {o['catchers_real_sample']['real_best_framer']:.0%} | "
        f"{o['catchers_real_sample']['main_catcher_max']:.0%} / {o['catchers_real_sample']['main_catcher_median']:.0%} | |",
        "",
        "Without the cap the optimizer catches its best framer more than any real catcher sustains, so its framing gain is cut "
        "(60-90% kept, as in the earlier verification). With the cap no catcher exceeds 70%, so the gain is counted in full.",
        "",
    ]
    if NOTES.exists():
        L += ["", NOTES.read_text(encoding="utf-8")]
    return "\n".join(L)


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("build", "all"):
        build()
    if cmd in ("score", "all"):
        out = score()
        REPORT.write_text(render(out), encoding="utf-8")
        print(render(out))
    if cmd == "report":
        REPORT.write_text(render(json.loads(RESULTS.read_text(encoding="utf-8"))), encoding="utf-8")


if __name__ == "__main__":
    main()
