"""Is the win model really worth +2.4 wins a season? Checks on the claim, then its value in dollars (no LLM).

The claim (evidence/tests/win_model_defense.md): on 150 sampled 2026 games, the v3 plan (code-built lineup with
defense, staff's starter) beats the real manager's lineup and starter by +1.47 win-probability points per game on
the season-stats lens, +2.4 wins per 162. The checks:

  1. Circularity. Re-score the same plans with an INDEPENDENT-DATA lens: every hitter, starter and fielder valued by
     what he did AFTER the game (rest of 2026; 2026 fielding instead of the 2023-25 ratings the optimizer used). Its
     errors share no data with the optimizer's inputs, so picking players on noise can't inflate it.
  2. Does the lens predict real games? Every 2026 team-game, real lineups and starters: regress runs actually scored
     on the lens's lineup, opposing-starter and opposing-defense parts, with team fixed effects (so only game-to-game
     choices within a team identify the slopes). Also August-September only.
  3. The starter over a season. Moving the next starter up a day is not free: the start he takes is one a later
     game loses. Replay each team's 2026 schedule with "start the best-rated starter on 4+ days of rest" against
     what really happened.
  4. Sensitivity to the defense weight and to rest days.
  5. The interval: games bootstrap plus the slopes' own uncertainty.
  6. Dollars: market price of a win, and playoff odds in a 12-team format by team situation.

Usage: python scripts/value_verification.py      (writes evidence/tests/value_verification.md; a few minutes)
"""

from __future__ import annotations

import json
import math
import sys
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import db  # noqa: E402
from backend.engine import defense as dfn  # noqa: E402
import win_model as wm  # noqa: E402

OUT_JSON = wm.SAVE / "value_verification.json"
REPORT = ROOT / "evidence" / "tests" / "value_verification.md"
NOTES = ROOT / "evidence" / "tests" / "value_verification_interpretation.md"   # hand-written; appended
SEED = 409
BOOT = 2000
TEST_FROM = "2026-08-01"


# ---------------------------------------------------------------------------
# A lens = how to value a hitter, a starter and a fielder. Runs are split into parts so each can be scaled.
# ---------------------------------------------------------------------------

def season_hitter(e: dict, d: str) -> float:
    return wm.shrink(e["woba"], e["n"], 200)


def season_pitcher(sp: dict, d: str) -> float:
    return wm.shrink(sp["woba"], sp["n"], 400)


def season_defense(pid: int, pos: str, d: str) -> float:
    return dfn.runs_saved(pid, pos, d, {"fielding": 1.0, "framing": 1.0})


class Future:
    """What each player did AFTER the game (rest of 2026). Shares no data with any pre-game input."""

    def __init__(self, k_hit: float, k_pitch: float):
        self.k_hit, self.k_pitch = k_hit, k_pitch
        self.bat = self._cumulative("SELECT batter_id id, game_date d, SUM(woba_num) n, SUM(woba_den) w "
                                    "FROM statcast_batter_game GROUP BY 1, 2 ORDER BY 1, 2")
        self.pit = self._cumulative("SELECT pitcher_id id, game_date d, SUM(woba_num) n, SUM(woba_den) w "
                                    "FROM statcast_pitcher_game GROUP BY 1, 2 ORDER BY 1, 2")
        self.field = {(r["player_id"], r["position"]): (r["fielding_runs_prevented"] or 0.0, r["innings"] or 0.0)
                      for r in db.rows("SELECT * FROM fielding_by_position WHERE season = 2026")}
        self.frame = {r["player_id"]: (r["framing_runs"] or 0.0, r["pitches"] or 0.0)
                      for r in db.rows("SELECT * FROM framing_history WHERE season = 2026")}
        self.played = {r["player_id"] for r in db.rows("SELECT DISTINCT player_id FROM fielding_by_position "
                                                       "WHERE season = 2026 AND innings > 0")}

    @staticmethod
    def _cumulative(sql: str) -> dict:
        out: dict = defaultdict(lambda: ([], [], []))
        for r in db.rows(sql):
            dates, num, den = out[r["id"]]
            dates.append(r["d"]); num.append((num[-1] if num else 0.0) + (r["n"] or 0.0))
            den.append((den[-1] if den else 0.0) + (r["w"] or 0.0))
        return dict(out)

    @staticmethod
    def _after(table: dict, pid: int, d: str) -> tuple[float, float]:
        if pid not in table:
            return 0.0, 0.0
        dates, num, den = table[pid]
        i = bisect_right(dates, d)          # rows dated <= d are excluded
        before_n, before_w = (num[i - 1], den[i - 1]) if i else (0.0, 0.0)
        return num[-1] - before_n, den[-1] - before_w

    def hitter(self, e: dict, d: str) -> float:
        n, w = self._after(self.bat, e["pid"], d)
        return (n + wm.LEAGUE * self.k_hit) / (w + self.k_hit) if w + self.k_hit else wm.LEAGUE

    def pitcher(self, sp: dict, d: str) -> float:
        n, w = self._after(self.pit, sp["pid"], d)
        return (n + wm.LEAGUE * self.k_pitch) / (w + self.k_pitch) if w + self.k_pitch else wm.LEAGUE

    def defense(self, pid: int, pos: str, d: str) -> float:
        if pos == "DH":
            return 0.0
        if pos == "C":
            fr, n = self.frame.get(pid, (0.0, 0.0))
            return dfn.PITCHES_PER_GAME * fr / n if n else 0.0
        frp, inn = self.field.get((pid, pos), (0.0, 0.0))
        if inn >= 1:
            return 9 * frp / inn
        s = dfn.rating_settings()
        return s["new_position_per_game"] if pid in self.played else s["no_history_per_game"]


def run_parts(lineup: list[dict], opp_sp: dict, d: str, hv, pv) -> tuple[float, float]:
    """(lineup part, opposing-starter part) of expected runs above league, as in win_model.expected_runs."""
    adv, same = wm.platoon_split()
    share = min(wm.starter_depth(opp_sp["pid"], d) / wm.TEAM_PA, 0.9)
    p = pv(opp_sp, d) - wm.LEAGUE
    lin = sp = 0.0
    for e in lineup:
        h = hv(e, d) - wm.LEAGUE
        lin += wm.SLOT_PA[e["slot"]] * (h + share * (adv if e["edge"] else same))
        sp += wm.SLOT_PA[e["slot"]] * share * p
    return lin / 1.2, sp / 1.2


def team_def(players: list[tuple[int, str]], d: str, dv) -> float:
    return sum(dv(p, q, d) for p, q in players)


def game_prob(c: dict, lineup: list[dict], pos: dict, sp: dict, lens: dict, b=(1.0, 1.0, 1.0)) -> tuple[float, dict]:
    """P(our team wins) with this lineup and starter; b scales (lineup, starter, defense). Returns the parts too."""
    hv, pv, dv = lens["hitter"], lens["pitcher"], lens["defense"]
    bl, bs, bd = b
    opp = c["opp_real"] if sp["pid"] == c["real"]["sp"]["pid"] else c["opp_vs_plan_sp"]
    our_lin, our_vs_sp = run_parts(lineup, c["opp_sp"], c["date"], hv, pv)
    opp_lin, opp_vs_sp = run_parts(opp, sp, c["date"], hv, pv)
    ours = team_def([(e["pid"], pos[e["pid"]]) for e in lineup], c["date"], dv)
    theirs = team_def([(e["pid"], c["opp_pos"][e["pid"]]) for e in opp], c["date"], dv)
    rs = wm.LG_RPG + bl * our_lin + our_vs_sp - bd * theirs
    ra = wm.LG_RPG + opp_lin + bs * opp_vs_sp - bd * ours
    parts = {"lin": our_lin, "sp": opp_vs_sp, "def": ours, "opp_lin": opp_lin, "rs": max(rs, 0.5), "ra": max(ra, 0.5)}
    return wm.win_prob(max(rs, 0.5), max(ra, 0.5), c["home"], wm.Params()), parts


def load_cases(version: str) -> list[dict]:
    folder = wm.VERSIONS[version][1]
    cases = []
    for c in wm.plan_cases(folder):
        gpk = int(c["run"].split("_g")[1].split("_")[0])
        g = db.one("SELECT home_team_id h, away_team_id a FROM games WHERE game_pk = ?", gpk)
        opp_id = g["a"] if g["h"] == c["team_id"] else g["h"]
        c = dict(c, gpk=gpk, opp_pos=wm.real_positions(gpk, opp_id), real_pos=wm.real_positions(gpk, c["team_id"]),
                 plan_pos=wm.plan_positions(folder, c["run"]))
        cases.append(c)
    return sorted(cases, key=lambda c: c["run"])


def edges(cases: list[dict], lens: dict, b=(1.0, 1.0, 1.0)) -> dict[str, np.ndarray]:
    """Per-game edge (plan minus real) for lineup + starter, lineup only, starter only."""
    both, lin, sp = [], [], []
    for c in cases:
        real = game_prob(c, c["real"]["lineup"], c["real_pos"], c["real"]["sp"], lens, b)[0]
        both.append(game_prob(c, c["plan"]["lineup"], c["plan_pos"], c["plan"]["sp"], lens, b)[0] - real)
        lin.append(game_prob(c, c["plan"]["lineup"], c["plan_pos"], c["real"]["sp"], lens, b)[0] - real)
        sp.append(game_prob(c, c["real"]["lineup"], c["real_pos"], c["plan"]["sp"], lens, b)[0] - real)
    return {"both": np.array(both), "lineup": np.array(lin), "starter": np.array(sp)}


def split_lineup(cases: list[dict], lens: dict) -> dict[str, np.ndarray]:
    """The lineup edge split into its offense part and its defense part (same lens)."""
    off, de = [], []
    for c in cases:
        real = game_prob(c, c["real"]["lineup"], c["real_pos"], c["real"]["sp"], lens)[0]
        no_def = dict(lens, defense=lambda p, q, d: 0.0)
        r0 = game_prob(c, c["real"]["lineup"], c["real_pos"], c["real"]["sp"], no_def)[0]
        p0 = game_prob(c, c["plan"]["lineup"], c["plan_pos"], c["real"]["sp"], no_def)[0]
        full = game_prob(c, c["plan"]["lineup"], c["plan_pos"], c["real"]["sp"], lens)[0]
        off.append(p0 - r0)
        de.append((full - real) - (p0 - r0))
    return {"offense": np.array(off), "defense": np.array(de)}


def boot(x: np.ndarray, rng: np.random.Generator, n: int = BOOT) -> list[float]:
    idx = rng.integers(0, len(x), (n, len(x)))
    return np.percentile(x[idx].mean(axis=1), [2.5, 97.5]).tolist()


# ---------------------------------------------------------------------------
# Check 2: do the lens's parts predict real runs? (every 2026 team-game, team fixed effects)
# ---------------------------------------------------------------------------

def team_game_table(lens: dict) -> list[dict]:
    games = json.loads(wm.FEATURES.read_text(encoding="utf-8"))
    pos = {(r["game_pk"], r["player_id"]): r["start_position"] for r in db.rows(
        "SELECT game_pk, player_id, start_position FROM batting_lines WHERE is_starter = 1")}
    score = {r["game_pk"]: (r["home_score"], r["away_score"]) for r in db.rows("SELECT game_pk, home_score, away_score FROM games")}
    out = []
    for g in games:
        hs, as_ = score[g["game_pk"]]
        for us, them, runs in (("home", "away", hs), ("away", "home", as_)):
            lin, sp = run_parts(g[us]["lineup"], g[them]["sp"], g["date"], lens["hitter"], lens["pitcher"])
            de = team_def([(e["pid"], pos[(g["game_pk"], e["pid"])]) for e in g[them]["lineup"]], g["date"], lens["defense"])
            out.append({"game_pk": g["game_pk"], "date": g["date"], "bat": g[us + "_id"], "fld": g[them + "_id"],
                        "home": us == "home", "runs": runs, "lin": lin, "sp": sp, "def": de,
                        "home_win": g["home_win"]})
    return out


def fe_regression(rows: list[dict], cols: list[str], fe: bool = True) -> np.ndarray:
    """OLS of runs on the lens parts (+ home), with batting-team and fielding-team fixed effects."""
    teams = sorted({r["bat"] for r in rows})
    ti = {t: i for i, t in enumerate(teams)}
    X = [[r[c] for c in cols] + [float(r["home"])] for r in rows]
    X = np.array(X)
    if fe:
        D1 = np.zeros((len(rows), len(teams))); D2 = np.zeros((len(rows), len(teams) - 1))
        for i, r in enumerate(rows):
            D1[i, ti[r["bat"]]] = 1
            if ti[r["fld"]] > 0:
                D2[i, ti[r["fld"]] - 1] = 1
        X = np.column_stack([X, D1, D2])
    else:
        X = np.column_stack([X, np.ones(len(rows))])
    y = np.array([r["runs"] for r in rows], float)
    return np.linalg.lstsq(X, y, rcond=None)[0][:len(cols)]


def slopes(rows: list[dict], rng: np.random.Generator, n_boot: int = 400) -> dict:
    """Slopes of real runs on each lens part; bootstrap resamples whole games (both sides together)."""
    cols = ["lin", "sp", "def"]
    by_game = defaultdict(list)
    for r in rows:
        by_game[r["game_pk"]].append(r)
    keys = list(by_game)
    point = fe_regression(rows, cols)
    draws = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(keys), len(keys))
        rs = [r for i in pick for r in by_game[keys[i]]]
        draws.append(fe_regression(rs, cols))
    draws = np.array(draws)
    return {"point": point.tolist(), "ci_low": np.percentile(draws, 2.5, axis=0).tolist(),
            "ci_high": np.percentile(draws, 97.5, axis=0).tolist(), "draws": draws.tolist(),
            "no_fe": fe_regression(rows, cols, fe=False).tolist(), "n": len(rows),
            "sd": [float(np.std([r[c] for r in rows])) for c in cols]}


def within_sd(rows: list[dict], col: str, key: str) -> float:
    """Spread of a lens part within a team (what the fixed-effects slope is identified from)."""
    by = defaultdict(list)
    for r in rows:
        by[r[key]].append(r[col])
    dev = [x - np.mean(v) for v in by.values() for x in v]
    return float(np.std(dev))


# ---------------------------------------------------------------------------
# Check 3: the starter choice over a whole season
# ---------------------------------------------------------------------------

def days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


@lru_cache(maxsize=1)
def starts_table() -> list[dict]:
    return db.rows("SELECT game_pk, game_date, team_id, player_id, bf FROM pitching_lines WHERE is_starter = 1 "
                   "ORDER BY team_id, game_date, game_pk")


def prev_start(pid: int, d: str) -> str | None:
    return db.one("SELECT MAX(game_date) d FROM pitching_lines WHERE player_id = ? AND is_starter = 1 AND game_date < ?",
                  pid, d)["d"]


def plan_starter_facts(cases: list[dict], e_sp: np.ndarray) -> dict:
    """For plans that changed the starter: his days of rest, and where the starter edge comes from."""
    rest, moved, other = [], [], []
    for c, x in zip(cases, e_sp):
        if c["same_sp"]:
            continue
        last = prev_start(c["plan"]["sp"]["pid"], c["date"])
        rest.append(days(last, c["date"]) - 1 if last else None)
        (moved if c["moved_up"] else other).append(x)
    known = [r for r in rest if r is not None]
    return {"changed": len(rest), "moved_up": len(moved), "other": len(other),
            "edge_moved_up": float(np.sum(moved)) / len(cases), "edge_other": float(np.sum(other)) / len(cases),
            "rest_days": {str(k): known.count(k) for k in sorted(set(known))}, "rest_unknown": rest.count(None)}


def runs_vs_starter(p_woba: float, depth_bf: float) -> float:
    """Runs a starter of this quality costs (positive) or saves vs league average in one game (season-lens units)."""
    share = min(depth_bf / wm.TEAM_PA, 0.9)
    return share * sum(wm.SLOT_PA.values()) * (p_woba - wm.LEAGUE) / 1.2


def rotation_replay(cap_extra: int | None) -> dict:
    """Replay every team's 2026 schedule: each game, start the best-rated (pre-game, season lens) starter who is on
    the active roster, is part of the team's rotation around that date (started for the team within 12 days either
    side), and has 4+ days of rest in the REPLAYED schedule. Fall back to the real starter if nobody qualifies.
    cap_extra limits each pitcher to his real number of starts + cap_extra (None = no cap).
    Scored with each pitcher's pre-game value (what the per-game analysis used) and with his full-2026 value."""
    stints = defaultdict(list)
    for r in db.rows("SELECT team_id, player_id, start_date, end_date FROM roster_stints"):
        stints[(r["team_id"], r["player_id"])].append((r["start_date"], r["end_date"]))
    full = {r["pid"]: r["n"] / r["w"] for r in db.rows(
        "SELECT pitcher_id pid, SUM(woba_num) n, SUM(woba_den) w FROM statcast_pitcher_game GROUP BY 1") if r["w"]}
    by_team = defaultdict(list)
    real_starts = defaultdict(int)
    for r in starts_table():
        by_team[r["team_id"]].append(r)
        real_starts[(r["team_id"], r["player_id"])] += 1
    fut = Future(0, 200)
    out = {"games": 0, "changed": 0, "pre_runs": 0.0, "future_runs": 0.0, "naive_pre_runs": 0.0,
           "naive_future_runs": 0.0, "fallback": 0, "four_day": 0, "real_four_day": 0}
    top_extra = []

    def cost(p: int, d: str, lens: str) -> float:
        v = wm.shrink(*wm.pitcher(p, d), 400) if lens == "pre" else fut.pitcher({"pid": p}, d)
        return runs_vs_starter(v, wm.starter_depth(p, d))

    for team, games in by_team.items():
        last: dict[int, str] = {}
        real_last: dict[int, str] = {}
        count = defaultdict(int)
        dates_by_p = defaultdict(list)
        for g in games:
            dates_by_p[g["player_id"]].append(g["game_date"])
        for g in games:
            d, real = g["game_date"], g["player_id"]
            out["games"] += 1
            around = [p for p, ds in dates_by_p.items() if any(abs(days(x, d)) <= 12 for x in ds)
                      and any(a <= d <= b for a, b in stints.get((team, p), []))]
            # Naive, one game at a time (what a per-game comparison credits): best rested starter given the REAL
            # rest state, as if today's choice had no effect on later games.
            naive = [p for p in around if p not in real_last or days(real_last[p], d) >= 5]
            if naive:
                best = min(naive, key=lambda p: cost(p, d, "pre"))
                out["naive_pre_runs"] += cost(best, d, "pre") - cost(real, d, "pre")
                out["naive_future_runs"] += cost(best, d, "future") - cost(real, d, "future")
            # Season replay: today's choice uses up that pitcher's rest for the games that follow.
            pool = [p for p in around if (p not in last or days(last[p], d) >= 5)
                    and (cap_extra is None or count[p] < real_starts[(team, p)] + cap_extra)]
            pick = min(pool, key=lambda p: cost(p, d, "pre")) if pool else real
            if not pool:
                out["fallback"] += 1
            if pick != real:
                out["changed"] += 1
                out["pre_runs"] += cost(pick, d, "pre") - cost(real, d, "pre")
                out["future_runs"] += cost(pick, d, "future") - cost(real, d, "future")
            if pick in last and days(last[pick], d) == 5:
                out["four_day"] += 1
            if real in real_last and days(real_last[real], d) == 5:
                out["real_four_day"] += 1
            last[pick] = d
            real_last[real] = d
            count[pick] += 1
        top_extra.append(max(count[p] - real_starts[(team, p)] for p in count))
    n = out["games"]
    for k in ("pre_runs", "future_runs", "naive_pre_runs", "naive_future_runs"):
        out[k + "_per_game"] = out[k] / n
    out["kept_share_pre"] = out["pre_runs"] / out["naive_pre_runs"]
    out["kept_share_future"] = out["future_runs"] / out["naive_future_runs"]
    out["share_changed"] = out["changed"] / n
    out["top_extra_starts_mean"] = float(np.mean(top_extra))
    return out


def defense_reliability(rng: np.random.Generator) -> dict:
    """How much of a rated run of defense shows up the next season? Every 2026 player-position (and catcher), the
    2026 runs saved per game regressed on the 2023-25 rating the optimizer used, weighted by 2026 innings (pitches).
    A slope of 1 means the rating is fully realized; the gap is regression to the mean the rating didn't capture."""
    out = {}
    field = db.rows("SELECT player_id, position, innings, fielding_runs_prevented frp FROM fielding_by_position "
                    "WHERE season = 2026 AND innings > 0 AND position NOT IN ('C', 'DH', 'P')")
    x = np.array([dfn.fielding_per_game(r["player_id"], r["position"], 2025) for r in field])
    y = np.array([9 * (r["frp"] or 0.0) / r["innings"] for r in field])
    w = np.array([r["innings"] for r in field])
    regular = np.array([r["innings"] >= 300 for r in field])
    frame = db.rows("SELECT player_id, pitches, framing_runs FROM framing_history WHERE season = 2026 AND pitches > 0")
    xc = np.array([dfn.framing_per_game(r["player_id"], 2025) for r in frame])
    yc = np.array([dfn.PITCHES_PER_GAME * r["framing_runs"] / r["pitches"] for r in frame])
    wc = np.array([r["pitches"] for r in frame], float)
    sets = {"fielding": (x, y, w), "fielding_300_plus_innings": (x[regular], y[regular], w[regular]),
            "fielding_under_300_innings": (x[~regular], y[~regular], w[~regular]), "framing": (xc, yc, wc)}
    for name, (a, b, ww) in sets.items():
        def wls(i):
            A = np.column_stack([np.ones(len(i)), a[i]])
            W = ww[i]
            return np.linalg.solve(A.T @ (A * W[:, None]), A.T @ (W * b[i]))[1]
        idx = np.arange(len(a))
        draws = [wls(rng.integers(0, len(a), len(a))) for _ in range(1000)]
        out[name] = {"slope": float(wls(idx)), "ci": np.percentile(draws, [2.5, 97.5]).tolist(), "n": len(a)}
    return out


def prior_innings(pid: int, pos: str, last_season: int = 2025) -> float:
    return sum(dfn._history(pid, pos).get(last_season - i, (0.0, 0.0))[1] for i in range(3))


def bucket(pid: int, pos: str) -> str:
    """Pre-game information only: how established he is at this position in 2023-25."""
    inn = prior_innings(pid, pos)
    return "established (300+ innings there in 2023-25)" if inn >= 300 else \
        "part-time there (1-299 innings)" if inn > 0 else "new to the position"


def defense_calibration(rng: np.random.Generator) -> dict:
    """E[2026 runs saved per game | the optimizer's rating, how established he is there], fitted on every 2026
    player-position (innings-weighted). Unlike a single slope, the intercept per group catches a bias the rating
    has if, say, players new to a position do worse than the rating assumes."""
    field = db.rows("SELECT player_id, position, innings, fielding_runs_prevented frp FROM fielding_by_position "
                    "WHERE season = 2026 AND innings > 0 AND position NOT IN ('C', 'DH', 'P')")
    groups = defaultdict(list)
    for r in field:
        groups[bucket(r["player_id"], r["position"])].append(
            (dfn.fielding_per_game(r["player_id"], r["position"], 2025), 9 * (r["frp"] or 0.0) / r["innings"], r["innings"]))
    out = {}
    for g, v in groups.items():
        a = np.array(v)

        def wls(i):
            A = np.column_stack([np.ones(len(i)), a[i, 0]])
            W = a[i, 2]
            return np.linalg.solve(A.T @ (A * W[:, None]) + 1e-9 * np.eye(2), A.T @ (W * a[i, 1]))

        draws = np.array([wls(rng.integers(0, len(a), len(a))) for _ in range(1000)])
        b = wls(np.arange(len(a)))
        out[g] = {"intercept": float(b[0]), "slope": float(b[1]), "n": len(a), "innings": float(a[:, 2].sum()),
                  "mean_rating": float(np.average(a[:, 0], weights=a[:, 2])),
                  "mean_2026": float(np.average(a[:, 1], weights=a[:, 2])),
                  "intercept_ci": np.percentile(draws[:, 0], [2.5, 97.5]).tolist(),
                  "slope_ci": np.percentile(draws[:, 1], [2.5, 97.5]).tolist(), "draws": draws.tolist()}
    return out


def calibrated_defense(cal: dict, framing_slope: float, draw: int | None = None):
    """A defense lens: each fielder valued at what 2026 says his rating is really worth (see defense_calibration)."""
    def dv(pid: int, pos: str, d: str) -> float:
        if pos == "DH":
            return 0.0
        if pos == "C":
            return framing_slope * dfn.framing_per_game(pid, 2025)
        g = cal[bucket(pid, pos)]
        a, b = (g["intercept"], g["slope"]) if draw is None else g["draws"][draw]
        return a + b * dfn.fielding_per_game(pid, pos, 2025)
    return dv


def hitter_calibration() -> dict:
    """E[his wOBA over the rest of 2026 | the season lens's pre-game value], PA-weighted, every 2026 start."""
    games = json.loads(wm.FEATURES.read_text(encoding="utf-8"))
    fut = Future(0, 0)
    xs, ys, ws, ps = [], [], [], []
    for g in games:
        for side in ("home", "away"):
            for e in g[side]["lineup"]:
                n, w = fut._after(fut.bat, e["pid"], g["date"])
                if w >= 30:
                    xs.append(season_hitter(e, g["date"])); ys.append(n / w); ws.append(w); ps.append(e["pid"])
    x, y, w = map(np.array, (xs, ys, ws))

    def wls(i):
        A = np.column_stack([np.ones(len(i)), x[i]])
        return np.linalg.solve(A.T @ (A * w[i][:, None]), A.T @ (w[i] * y[i]))[1]

    rows_of = defaultdict(list)            # resample whole players: one hitter's rows are not independent
    for i, p in enumerate(ps):
        rows_of[p].append(i)
    players = list(rows_of)
    rng = np.random.default_rng(SEED)
    draws = [wls(np.array([i for k in rng.integers(0, len(players), len(players)) for i in rows_of[players[k]]]))
             for _ in range(300)]
    return {"slope": float(wls(np.arange(len(x)))), "ci": np.percentile(draws, [2.5, 97.5]).tolist(),
            "draws": [float(d) for d in draws], "n": len(x), "players": len(players)}


BUCKETS = ["established (300+ innings there in 2023-25)", "part-time there (1-299 innings)", "new to the position"]


def defense_terms(c: dict) -> dict:
    """Plan minus real, per game: fielders by group (count and summed rating) and the catcher's framing rating."""
    t = {"count": np.zeros(3), "rating": np.zeros(3), "framing": 0.0}
    for lineup, pos, s in ((c["plan"]["lineup"], c["plan_pos"], 1), (c["real"]["lineup"], c["real_pos"], -1)):
        for e in lineup:
            p = pos[e["pid"]]
            if p == "DH":
                continue
            if p == "C":
                t["framing"] += s * dfn.framing_per_game(e["pid"], 2025)
                continue
            i = BUCKETS.index(bucket(e["pid"], p))
            t["count"][i] += s
            t["rating"][i] += s * dfn.fielding_per_game(e["pid"], p, 2025)
    return t


def wp_per_run_allowed(c: dict, lens: dict) -> float:
    """How many win-probability points one run allowed costs in this game (season lens, real plan)."""
    _, parts = game_prob(c, c["real"]["lineup"], c["real_pos"], c["real"]["sp"], lens)
    rs, ra = parts["rs"], parts["ra"]
    P = wm.Params()
    return (wm.win_prob(rs, ra - 0.01, c["home"], P) - wm.win_prob(rs, ra + 0.01, c["home"], P)) / 0.02


# ---------------------------------------------------------------------------
# Check 6: playoff odds in a 12-team format
# ---------------------------------------------------------------------------

def playoff_odds(target_talent: list[float], delta: float, sims: int = 200_000, talent_sd: float = 9.5,
                 seed: int = SEED) -> dict:
    """30 teams, 2 leagues x 3 divisions of 5. Each team's talent ~ Normal(81, talent_sd) wins; its season is
    Binomial(162, talent/162). Six teams per league go: 3 division winners + the 3 best other records.
    The focal team (league 0, division 0) has the given talent, with and without +delta wins."""
    out = {}
    for t in target_talent:
        res = []
        for add in (0.0, delta):
            r2 = np.random.default_rng(seed)        # common random numbers: same seasons, only the focal team moves
            talent = np.clip(r2.normal(81, talent_sd, (sims, 30)), 40, 122)
            talent[:, 0] = t + add
            wins = r2.binomial(162, talent / 162) + r2.random((sims, 30)) * 0.5      # random tie-break
            lg = wins[:, :15]
            div_win = np.zeros((sims, 15), bool)
            for dv in range(3):
                block = lg[:, 5 * dv:5 * dv + 5]
                div_win[np.arange(sims), 5 * dv + block.argmax(axis=1)] = True
            others = np.where(div_win, -np.inf, lg)
            third_best = np.sort(others, axis=1)[:, -3]
            made = div_win[:, 0] | (others[:, 0] >= third_best)
            res.append(float(made.mean()))
        out[t] = {"base": res[0], "with": res[1], "gain": res[1] - res[0]}
    return out


def typical_team_gain(delta: float, sims: int = 400_000, talent_sd: float = 9.5, seed: int = SEED) -> float:
    """Playoff-odds gain from +delta wins for a team whose talent is drawn from the league distribution
    (the expectation over all 30 teams' situations, before you know which team adopts)."""
    res = []
    for add in (0.0, delta):
        r = np.random.default_rng(seed)
        talent = np.clip(r.normal(81, talent_sd, (sims, 30)), 40, 122)
        talent[:, 0] += add
        wins = r.binomial(162, talent / 162) + r.random((sims, 30)) * 0.5
        lg = wins[:, :15]
        div_win = np.zeros((sims, 15), bool)
        for dv in range(3):
            div_win[np.arange(sims), 5 * dv + lg[:, 5 * dv:5 * dv + 5].argmax(axis=1)] = True
        others = np.where(div_win, -np.inf, lg)
        res.append(float((div_win[:, 0] | (others[:, 0] >= np.sort(others, axis=1)[:, -3])).mean()))
    return res[1] - res[0]


def catcher_usage(cases: list[dict]) -> dict:
    """How often the plan and the real manager caught the team's best-rated framer, vs real catcher workloads."""
    from backend.engine import roster
    plan = real = n = 0
    for c in cases:
        cs = [r["player_id"] for r in roster.active_roster(c["team_id"], c["date"]) if r["position"] == "C"]
        if len(cs) < 2:
            continue
        n += 1
        best = max(cs, key=lambda p: dfn.framing_per_game(p, 2025))
        plan += next(e["pid"] for e in c["plan"]["lineup"] if c["plan_pos"][e["pid"]] == "C") == best
        real += next(e["pid"] for e in c["real"]["lineup"] if c["real_pos"][e["pid"]] == "C") == best
    starts = defaultdict(list)
    for r in db.rows("SELECT team_id, player_id, COUNT(*) n FROM batting_lines WHERE start_position = 'C' AND is_starter = 1 "
                     "GROUP BY 1, 2"):
        starts[r["team_id"]].append(r["n"])
    games = {r["team_id"]: r["g"] for r in db.rows("SELECT team_id, COUNT(DISTINCT game_pk) g FROM batting_lines GROUP BY 1")}
    share = [max(v) / games[t] for t, v in starts.items()]
    return {"plan_best_framer": plan / n, "real_best_framer": real / n, "main_catcher_max": max(share),
            "main_catcher_p90": float(np.percentile(share, 90)), "main_catcher_median": float(np.median(share))}


def rest_performance() -> dict:
    """Do starters pitch worse on exactly 4 days of rest than on 5+? Runs allowed per batter faced in that start,
    minus the same pitcher's 2026 average (so each pitcher is compared with himself)."""
    rows = db.rows("SELECT player_id, game_date, bf, r FROM pitching_lines WHERE is_starter = 1 AND bf > 0 "
                   "ORDER BY player_id, game_date")
    by_p = defaultdict(list)
    for r in rows:
        by_p[r["player_id"]].append(r)
    groups = {"4": [], "5": [], "6-10": []}
    for rs in by_p.values():
        base = sum(x["r"] for x in rs) / sum(x["bf"] for x in rs)
        for a, b in zip(rs, rs[1:]):
            rest = days(a["game_date"], b["game_date"]) - 1
            key = "4" if rest == 4 else "5" if rest == 5 else "6-10" if 6 <= rest <= 10 else None
            if key:
                groups[key].append((b["r"] / b["bf"] - base, b["bf"]))
    out = {}
    for k, v in groups.items():
        x = np.array([a for a, _ in v]); w = np.array([b for _, b in v], float)
        m = float(np.average(x, weights=w))
        se = float(np.sqrt(np.average((x - m) ** 2, weights=w) / len(x)))
        out[k] = {"starts": len(v), "runs_per_bf": m, "se": se, "runs_per_start": m * wm.STARTER_BF,
                  "se_per_start": se * wm.STARTER_BF}
    return out


# ---------------------------------------------------------------------------
# Putting it together
# ---------------------------------------------------------------------------

DOLLARS_PER_WIN = (8.0, 10.0, 12.0)         # $M per win on the free-agent market (FanGraphs-style $/WAR)
BERTH_VALUE = (15.0, 30.0, 50.0)            # $M a playoff berth is worth to the club after revenue sharing
SITUATIONS = {"Rebuilding (72-win talent)": 72, "Fringe (78)": 78, "Bubble (84)": 84, "Bubble+ (87)": 87,
              "Likely (90)": 90, "Lock (96)": 96}
CATCHER_WORKLOAD = (0.6, 0.76, 0.9)        # share of the framing gain a real catcher workload can sustain
KEPT_SHARE = (0.28, 0.44)                   # share of a per-game starter edge that survives a season replay


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    wm.load_constants()
    rng = np.random.default_rng(SEED)
    S = {"hitter": season_hitter, "pitcher": season_pitcher, "defense": season_defense}
    out: dict = {}
    cases = load_cases("v3")
    n = len(cases)
    e = edges(cases, S)
    lin_split = split_lineup(cases, S)
    out["claim"] = {k: float(v.mean()) for k, v in e.items()} | {k: float(v.mean()) for k, v in lin_split.items()}
    out["claim_ci_games_only"] = boot(e["both"], rng)
    for k in ("both", "lineup", "starter"):
        out["claim"][k + "_ci"] = boot(e[k], rng)
    for k in ("offense", "defense"):
        out["claim"][k + "_ci"] = boot(lin_split[k], rng)
    print("claim", out["claim"]["both"] * 162, flush=True)

    # 1. Circularity: the independent-data lens
    out["independent"] = {}
    for label, (kh, kp) in {"unregressed": (0, 0), "regressed (100 PA / 200 BF)": (100, 200)}.items():
        F = Future(kh, kp)
        L = {"hitter": F.hitter, "pitcher": F.pitcher, "defense": F.defense}
        ee, ss = edges(cases, L), split_lineup(cases, L)
        out["independent"][label] = {k: [float(v.mean()), *boot(v, rng)] for k, v in (ee | ss).items()}
    print("independent done", flush=True)

    # 2. Does the lens predict real runs?
    rows = team_game_table(S)
    out["slopes"] = {"all": slopes(rows, rng), "aug_sep": slopes([r for r in rows if r["date"] >= TEST_FROM], rng),
                     "apr_jul": slopes([r for r in rows if r["date"] < TEST_FROM], rng)}
    out["within_sd"] = {c: within_sd(rows, c, k) for c, k in (("lin", "bat"), ("sp", "fld"), ("def", "fld"))}
    hit = hitter_calibration()
    out["hitter_calibration"] = {k: v for k, v in hit.items() if k != "draws"}
    rel = defense_reliability(rng)
    cal = defense_calibration(rng)
    out["defense_reliability"] = rel
    out["defense_calibration"] = {k: {a: b for a, b in v.items() if a != "draws"} for k, v in cal.items()}
    print("slopes done", flush=True)

    # 3. Starter over a season
    out["starter_facts"] = plan_starter_facts(cases, e["starter"])
    out["rest_performance"] = rest_performance()
    out["replay"] = {str(cap): rotation_replay(cap) for cap in (None, 2, 0)}
    print("replay done", flush=True)

    # 4. Sensitivity: defense weight, rest days
    out["defense_weight"] = {str(w): float(edges(cases, S, (1.0, 1.0, w))["both"].mean()) for w in (0.0, 0.5, 1.0)}
    folder = wm.VERSIONS["v3"][1]
    tired = []
    for c in cases:
        plan = json.loads((folder / c["run"] / "plan.json").read_text(encoding="utf-8"))
        st = {x["player_id"]: x["status"] for x in plan["sections"]["medical_report"]["statuses"]}
        tired.append(any(st.get(x["pid"]) == "rest_suggested" for x in c["added"]))
    tired = np.array(tired)
    out["catchers"] = catcher_usage(cases)
    out["rest"] = {"plans": int(tired.sum()), "lineup_edge_from_them": float(e["lineup"][tired].sum() / n),
                   "both_without_their_lineup_edge": float((e["both"] - np.where(tired, e["lineup"], 0)).mean())}

    # 5. The verified estimate: each piece scaled by what held-out data says it is worth
    k = np.array([wp_per_run_allowed(c, S) for c in cases])
    T = [defense_terms(c) for c in cases]
    cnt = np.array([t["count"] for t in T]); rat = np.array([t["rating"] for t in T]); frm = np.array([t["framing"] for t in T])
    off, sp = lin_split["offense"], e["starter"]
    resid = e["both"] - e["lineup"] - e["starter"]          # small interaction term, kept as is
    sp_draws = np.array(out["slopes"]["all"]["draws"])[:, 1]

    def verified(idx, hs, a, s, fs, wf, bs, kept):
        d = k[idx] * ((cnt[idx] * a).sum(1) + (rat[idx] * s).sum(1) + fs * wf * frm[idx])
        parts = {"offense": hs * off[idx], "defense": d, "starter": bs * kept * sp[idx], "interaction": resid[idx]}
        return {p: float(v.mean()) for p, v in parts.items()}

    a0 = np.array([cal[b]["intercept"] for b in BUCKETS]); s0 = np.array([cal[b]["slope"] for b in BUCKETS])
    point = verified(np.arange(n), hit["slope"], a0, s0, rel["framing"]["slope"], CATCHER_WORKLOAD[1],
                     out["slopes"]["all"]["point"][1], float(np.mean(KEPT_SHARE)))
    sims = []
    for _ in range(BOOT):
        j = rng.integers(0, 1000)
        a = np.array([cal[b]["draws"][j][0] for b in BUCKETS]); s = np.array([cal[b]["draws"][j][1] for b in BUCKETS])
        fs = rng.uniform(*rel["framing"]["ci"])
        sims.append(sum(verified(rng.integers(0, n, n), rng.choice(hit["draws"]), a, s, fs,
                                 rng.uniform(CATCHER_WORKLOAD[0], CATCHER_WORKLOAD[2]), rng.choice(sp_draws),
                                 rng.uniform(*KEPT_SHARE)).values()))
    out["verified"] = {"parts": point, "total": sum(point.values()), "ci": np.percentile(sims, [2.5, 97.5]).tolist(),
                       "p_positive": float(np.mean(np.array(sims) > 0))}
    # A floor: only what the independent-data check on these very plans confirms (framing at catcher, the starter
    # after the season replay); fielding and offense counted at zero.
    frame_only = float(np.mean(k * rel["framing"]["slope"] * CATCHER_WORKLOAD[1] * frm))
    out["floor"] = frame_only + point["starter"]
    print("verified", 162 * out["verified"]["total"], [162 * x for x in out["verified"]["ci"]], flush=True)

    for s in out["slopes"].values():
        s.pop("draws")
    dollars(out)
    write(out)


DECAY = {"Fast copying (edge halves each season, like Moneyball's OBP edge)": 0.5,
         "Slow copying (edge keeps 75% each season)": 0.75}
LICENSE_SHARE = (0.10, 0.20)        # share of the expected first-mover value a team might pay a vendor


def dollars(out: dict) -> None:
    """Check 6: the verified wins in dollars, for one team (first mover) and for the league."""
    # Low end = the floor (model uncertainty included), not the narrower calibration-model interval.
    W, lo, hi = 162 * out["verified"]["total"], 162 * out["floor"], 162 * out["verified"]["ci"][1]
    lo_ = max(lo, 0.05)
    d = {"wins": [lo, W, hi], "market": {str(p): [lo * p, W * p, hi * p] for p in DOLLARS_PER_WIN}, "playoffs": {}}
    for name, t in SITUATIONS.items():
        g = {x: playoff_odds([t], x)[t] for x in (lo_, W, hi)}
        d["playoffs"][name] = {"base": g[W]["base"], "gain": [g[lo_]["gain"], g[W]["gain"], g[hi]["gain"]],
                               "value": {str(v): [g[lo_]["gain"] * v, g[W]["gain"] * v, g[hi]["gain"] * v]
                                         for v in BERTH_VALUE}}
    d["typical_gain"] = [typical_team_gain(x) for x in (lo_, W)]
    # First mover: one season, then a head start of 1-3 seasons while rivals copy (undiscounted)
    mid_price, mid_berth = DOLLARS_PER_WIN[1], BERTH_VALUE[1]
    per_season = {
        "market, verified": W * mid_price, "market, low end": lo_ * mid_price,
        "playoffs typical, verified": d["typical_gain"][1] * mid_berth, "playoffs typical, low end": d["typical_gain"][0] * mid_berth,
        "playoffs bubble, verified": d["playoffs"]["Bubble (84)"]["gain"][1] * mid_berth,
        "playoffs bubble, low end": d["playoffs"]["Bubble (84)"]["gain"][0] * mid_berth,
    }
    d["first_mover"] = {"per_season": per_season, "head_start": {
        name: {k: [v * sum(r ** i for i in range(years)) for years in (1, 2, 3)] for k, v in per_season.items()}
        for name, r in DECAY.items()}}
    three = d["first_mover"]["head_start"]
    low3 = min(three[n]["market, low end"][2] for n in three)
    d["license"] = [LICENSE_SHARE[0] * per_season["market, low end"], LICENSE_SHARE[1] * per_season["market, verified"], low3]
    d["claimed_playoffs"] = {name: playoff_odds([t], 162 * out["claim"]["both"])[t]["gain"] for name, t in SITUATIONS.items()}
    out["dollars"] = d


def write(out: dict) -> None:
    OUT_JSON.write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    text = render(out)
    if NOTES.exists():
        text += "\n" + NOTES.read_text(encoding="utf-8")
    REPORT.write_text(text, encoding="utf-8")
    print(text)


def render(o: dict) -> str:
    w = lambda x: f"{162 * x:+.1f}"  # noqa: E731
    wr = lambda v: f"{162 * v[0]:+.1f} ({162 * v[1]:+.1f} to {162 * v[2]:+.1f})"  # noqa: E731
    C, V = o["claim"], o["verified"]
    ind = o["independent"]
    sl = o["slopes"]
    rp = o["replay"]
    sf = o["starter_facts"]
    rest = o["rest_performance"]
    cal, rel, hc = o["defense_calibration"], o["defense_reliability"], o["hitter_calibration"]
    D = o["dollars"]
    FM = D["first_mover"]["per_season"]
    fmt_s = lambda s, i: f"{s['point'][i]:+.2f} ({s['ci_low'][i]:+.2f} to {s['ci_high'][i]:+.2f})"  # noqa: E731
    L = [
        "# Is the win model really worth +2.4 wins a season? A verification",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `scripts/value_verification.py` (no LLM calls, no new plans; "
        "the same 150 v3 plans as `win_model_defense.md`). Numbers: `evidence/logs/win_impact/value_verification.json`. "
        "Wins are per 162 games; a win-probability point per game is 1.6 wins a season.",
        "",
        "## The claim, split into its pieces (season-stats lens, as reported)",
        "",
        "| Piece | Wins per 162 | 95% range (games bootstrap) |",
        "|---|---|---|",
        f"| Lineup: offense | {w(C['offense'])} | {w(C['offense_ci'][0])} to {w(C['offense_ci'][1])} |",
        f"| Lineup: defense (fielding + framing) | {w(C['defense'])} | {w(C['defense_ci'][0])} to {w(C['defense_ci'][1])} |",
        f"| Starter (mostly moving the next starter up a day) | {w(C['starter'])} | {w(C['starter_ci'][0])} to {w(C['starter_ci'][1])} |",
        f"| **Total** | **{w(C['both'])}** | {w(C['both_ci'][0])} to {w(C['both_ci'][1])} |",
        "",
        "The lineup's offense is a small part of the claim. Most of it is defense and the starter.",
        "",
        "## Check 1: circularity",
        "",
        "Defense counts the same way in the lens and in the optimizer: the same 2023-25 ratings, the same 1.0 weight. "
        f"So the defense piece, {C['defense'] / C['both']:.0%} of the claim, is the optimizer graded on its own yardstick. "
        "The starter piece uses the same "
        "starter rating (wOBA allowed, regressed at 400 batters faced) in both. Only the hitter values differ (lens: wOBA "
        "with the league platoon split; optimizer: xwOBA with the hitter's own split), and those two share the same plate appearances.",
        "",
        "**Independent-data lens.** The same plans re-scored with what every player did *after* the game: hitters' and "
        "starters' rest-of-2026 wOBA, and fielders' and catchers' 2026 defense instead of the 2023-25 ratings. None of this data was "
        "available to the optimizer, so picking players on lucky numbers can't inflate it. Its own noise is large.",
        "",
        "| Piece | Claimed | Independent lens, unregressed | Independent lens, regressed |",
        "|---|---|---|---|",
    ]
    u, r = ind["unregressed"], ind["regressed (100 PA / 200 BF)"]
    for key, label in (("offense", "Lineup: offense"), ("defense", "Lineup: defense"), ("starter", "Starter"), ("both", "**Total**")):
        L.append(f"| {label} | {w(C[key])} | {wr(u[key])} | {wr(r[key])} |")
    L += [
        "",
        "## Check 2: does the lens predict real runs?",
        "",
        f"Every 2026 team-game ({sl['all']['n']:,}), real lineups and starters. Runs actually scored are regressed on the "
        "lens's three parts, with batting-team and fielding-team fixed effects. Only game-to-game changes within a team "
        "(who plays, who starts) identify the slopes, and those are the choices the app makes. A slope of 1 means the lens's "
        "run estimates are right on average, and 0 means they predict nothing. The lens's parameters were set before 2026 (2025 "
        "league numbers, standard constants), so August-September is a clean hold-out. The one exception is the defense "
        "weight of 1.0, which was set from all 2026 games.",
        "",
        "| Lens part (runs) | Within-team spread (SD) | Slope, all 2026 | Slope, Aug-Sep only | Slope without team effects |",
        "|---|---|---|---|---|",
        f"| Our lineup's offense | {o['within_sd']['lin']:.3f} | {fmt_s(sl['all'], 0)} | {fmt_s(sl['aug_sep'], 0)} | {sl['all']['no_fe'][0]:+.2f} |",
        f"| Opposing starter's quality | {o['within_sd']['sp']:.3f} | {fmt_s(sl['all'], 1)} | {fmt_s(sl['aug_sep'], 1)} | {sl['all']['no_fe'][1]:+.2f} |",
        f"| Opposing defense (expect −1) | {o['within_sd']['def']:.3f} | {fmt_s(sl['all'], 2)} | {fmt_s(sl['aug_sep'], 2)} | {sl['all']['no_fe'][2]:+.2f} |",
        "",
        "Single games are noisy (about ±3 runs), so these slopes are imprecise. Player-level checks have far more data. "
        "Each one asks how much of a rated difference shows up later, in data the rating never saw:",
        "",
        "| Rating | What it predicts | Slope (1 = fully realized) | 95% range |",
        "|---|---|---|---|",
        f"| Lens hitter value (wOBA, regressed at 200 PA) | His wOBA over the rest of 2026 ({hc['n']:,} starts, {hc['players']} hitters) | "
        f"{hc['slope']:.2f} | {hc['ci'][0]:.2f} to {hc['ci'][1]:.2f} |",
        f"| Fielding rating, 2023-25 | His 2026 runs prevented at that position ({rel['fielding']['n']} player-positions) | "
        f"{rel['fielding']['slope']:.2f} | {rel['fielding']['ci'][0]:.2f} to {rel['fielding']['ci'][1]:.2f} |",
        f"| Framing rating, 2023-25 | His 2026 framing ({rel['framing']['n']} catchers) | {rel['framing']['slope']:.2f} | "
        f"{rel['framing']['ci'][0]:.2f} to {rel['framing']['ci'][1]:.2f} |",
        "",
        "Fielding by how established the player was at the position (pre-game information), innings-weighted:",
        "",
        "| Group | Player-positions | Mean rating | Mean 2026 result | Intercept | Slope |",
        "|---|---|---|---|---|---|",
        *[f"| {g} | {v['n']} | {v['mean_rating']:+.3f} | {v['mean_2026']:+.3f} | {v['intercept']:+.3f} "
          f"({v['intercept_ci'][0]:+.3f} to {v['intercept_ci'][1]:+.3f}) | {v['slope']:.2f} ({v['slope_ci'][0]:.2f} to {v['slope_ci'][1]:.2f}) |"
          for g, v in cal.items()],
        "",
        "## Check 3: the starter over a full season",
        "",
        f"{sf['changed']} of 150 plans changed the starter; {sf['moved_up']} moved the team's next starter up "
        f"(worth {w(sf['edge_moved_up'])} wins of the claim), and the other {sf['other']} were worth {w(sf['edge_other'])}. "
        f"Days of rest for the starters we chose: {', '.join(f'{k}: {v}' for k, v in sf['rest_days'].items())}.",
        "",
        "A one-game comparison treats today's start as free. It isn't: the pitcher we move up is not available for the "
        "game he would have started, and someone worse starts that one. **Season replay:** every team's 2026 schedule, "
        "replayed with the rule \"start the best-rated starter on the active roster with 4+ days of rest\". Each choice "
        "uses up that pitcher's rest for the games that follow. The \"one game at a time\" column applies the same rule to "
        "the real rest state each day, which is what the 150-game analysis credits.",
        "",
        "| Rule | Starts changed | Runs saved per game, one game at a time | Runs saved per game, season replay | Share kept | Same, judged on rest-of-season results | Extra starts for each team's top gainer |",
        "|---|---|---|---|---|---|---|",
        *[f"| {lab} | {rp[k]['share_changed']:.0%} | {-rp[k]['naive_pre_runs_per_game']:.3f} | {-rp[k]['pre_runs_per_game']:.3f} | "
          f"{rp[k]['kept_share_pre']:.0%} | {-rp[k]['naive_future_runs_per_game']:.3f} vs {-rp[k]['future_runs_per_game']:.3f} | "
          f"+{rp[k]['top_extra_starts_mean']:.1f} |"
          for k, lab in (("None", "No workload cap"), ("2", "At most 2 starts more than he really made"),
                         ("0", "No more starts than he really made"))],
        "",
        f"Does 4 days of rest hurt? Starters' runs allowed per start vs their own 2026 average: 4 days "
        f"{rest['4']['runs_per_start']:+.2f} (±{rest['4']['se_per_start']:.2f}, {rest['4']['starts']} starts), 5 days "
        f"{rest['5']['runs_per_start']:+.2f} (±{rest['5']['se_per_start']:.2f}), 6-10 days {rest['6-10']['runs_per_start']:+.2f} "
        f"(±{rest['6-10']['se_per_start']:.2f}). There's no measurable same-day penalty. The real costs of more starts "
        "for the best starters are innings limits and injury risk, which this data can't price.",
        "",
        "## Check 4: sensitivity to the defense weight and to rest days",
        "",
        "| Defense weight in the lens (plans unchanged) | 0 | 0.5 | 1.0 (as used) |",
        "|---|---|---|---|",
        f"| Total edge, wins per 162 | {w(o['defense_weight']['0.0'])} | {w(o['defense_weight']['0.5'])} | {w(o['defense_weight']['1.0'])} |",
        "",
        f"**Rest days.** {o['rest']['plans']} of 150 plans started a player the Team Doctor flagged for rest, where the real manager benched him. "
        f"Those lineups account for {w(o['rest']['lineup_edge_from_them'])} wins of the claim. If every one of those "
        "rest days has to be taken on another day anyway (rest is zero-sum over a season), the total falls to "
        f"{w(o['rest']['both_without_their_lineup_edge'])}. The same-day fatigue cost measured in 2026 was zero "
        "(`lineup_params.md`), but that test can't see injuries or late-season wear.",
        "",
        "## Check 5: the interval",
        "",
        f"The published +1.8 to +3.0 is a bootstrap over the 150 games with the lens held fixed ({w(o['claim_ci_games_only'][0])} "
        f"to {w(o['claim_ci_games_only'][1])} here). It covers which games were sampled, but not whether the lens's numbers are "
        "right. The verified estimate below scales each piece by what held-out data says it is worth, and its interval "
        f"redraws the games and every scaling factor together ({BOOT:,} draws):",
        "",
        "- **Offense** × the hitter-value slope (bootstrap by player).",
        "- **Defense**, re-valued at what 2026 says each fielder's rating is worth: intercept and slope by group, bootstrap draws. "
        f"The framing gain is then × the framing slope (drawn across its range) × a catcher-workload factor "
        f"({CATCHER_WORKLOAD[0]:.2f}-{CATCHER_WORKLOAD[2]:.2f}). The plans used the team's best-framing catcher in "
        f"{o['catchers']['plan_best_framer']:.0%} of games (real managers: {o['catchers']['real_best_framer']:.0%}), but no "
        f"2026 team's main catcher started more than {o['catchers']['main_catcher_max']:.0%} of its games, and the 90th "
        f"percentile was {o['catchers']['main_catcher_p90']:.0%}.",
        f"- **Starter** × the within-team starter slope (bootstrap draws) × the share a season replay keeps "
        f"({KEPT_SHARE[0]:.0%}-{KEPT_SHARE[1]:.0%}).",
        "",
        "| Piece | Claimed | Verified |",
        "|---|---|---|",
        f"| Lineup: offense | {w(C['offense'])} | {w(V['parts']['offense'])} |",
        f"| Lineup: defense | {w(C['defense'])} | {w(V['parts']['defense'])} |",
        f"| Starter | {w(C['starter'])} | {w(V['parts']['starter'])} |",
        f"| Interaction (lineup × starter) | {w(C['both'] - C['lineup'] - C['starter'])} | {w(V['parts']['interaction'])} |",
        f"| **Total, wins per 162** | **{w(C['both'])}** (+1.8 to +3.0) | **{w(V['total'])}** ({w(V['ci'][0])} to {w(V['ci'][1])} "
        "within the calibration model) |",
        f"| **Honest range, adding model uncertainty** | | **{w(o['floor'])} to {w(V['ci'][1])}** |",
        "",
        f"Within the calibration model the edge is above zero in {V['p_positive']:.0%} of draws. That model has one weak "
        "spot. It values fielding by how well the ratings predict 2026 defense *across all players*, where they hold up "
        "(slope about 1). But the direct check on *these* plans' fielders (Check 1) doesn't show the fielding gain at "
        "all. That check is noisy and has a selection problem: players who got few 2026 innings at a position often lost "
        "them by fielding badly. Still, it is a real warning. So the honest range runs down to a **floor of "
        f"{w(o['floor'])} wins**: the pieces that the direct check on these same plans confirms (catcher framing, cut for "
        "catcher workload, and the starter after the season replay), with fielding and offense counted at zero.",
        "",
        "## Check 6: expected value in dollars",
        "",
        "Every figure here is an estimate built on the stated assumptions. All of them start from the verified wins "
        f"({D['wins'][1]:+.1f}; conservative low end {max(D['wins'][0], 0.05):+.1f}, the floor), never the original +2.4. "
        "Two views of the same "
        "wins follow: what the market charges for a win, and what the wins do to playoff odds. They are alternatives, not "
        "additions, because the market price of a win already reflects the revenue that winning brings.",
        "",
        "### The headline: value to ONE team that adopts first",
        "",
        "The measured edge is against what real 2026 managers actually did. So it is already a first-mover figure: one "
        "team using the app while the other 29 keep managing as they do today.",
        "",
        "**Per season, in expectation** ($10M per win; $30M per playoff berth to the club):",
        "",
        "| View | At the verified estimate | At the conservative low end (the floor) |",
        "|---|---|---|",
        f"| Market price of the wins | **${FM['market, verified']:.1f}M** | ${FM['market, low end']:.1f}M |",
        f"| Playoff odds, typical team (talent drawn from the league spread) | ${FM['playoffs typical, verified']:.1f}M "
        f"({100 * D['typical_gain'][1]:+.1f} pts) | ${FM['playoffs typical, low end']:.1f}M ({100 * D['typical_gain'][0]:+.1f} pts) |",
        f"| Playoff odds, bubble team (84-win talent) | ${FM['playoffs bubble, verified']:.1f}M "
        f"({100 * D['playoffs']['Bubble (84)']['gain'][1]:+.1f} pts) | ${FM['playoffs bubble, low end']:.1f}M "
        f"({100 * D['playoffs']['Bubble (84)']['gain'][0]:+.1f} pts) |",
        "",
        "**Over a head start**, cumulative and undiscounted, if rivals copy the approach. With the original Moneyball, the "
        "market's under-pricing of on-base percentage was found to have largely corrected by 2004, the season after the "
        "book (Hakes & Sauer, *Journal of Economic Perspectives*, 2006). So fast copying is the realistic case. The methods "
        "here (defense, framing, rotation use) are already known to front offices, which argues for fast copying too:",
        "",
        "| Copying speed | Measure | 1 season | 2 seasons | 3 seasons |",
        "|---|---|---|---|---|",
        *[f"| {name} | {label} | ${v[0]:.1f}M | ${v[1]:.1f}M | ${v[2]:.1f}M |"
          for name, rows in D["first_mover"]["head_start"].items()
          for label, v in rows.items() if label in ("market, verified", "market, low end", "playoffs bubble, verified",
                                                     "playoffs bubble, low end")],
        "",
        "**Market price of a win.** Teams pay roughly $8-12M per win (WAR) in free agency: about $8M per win in "
        "FanGraphs-based estimates, and about $8.3M for hitters and $11.6M for pitchers in an informal 2025 count. The "
        "verified wins, priced like free-agent wins, per season:",
        "",
        "| $ per win | Low end | Verified | High end |",
        "|---|---|---|---|",
        *[f"| ${float(p):.0f}M | ${v[0]:.1f}M | **${v[1]:.1f}M** | ${v[2]:.1f}M |" for p, v in D["market"].items()],
        "",
        "**Playoff odds.** Simulated league: 30 teams, two leagues of three five-team divisions. Team talent ~ Normal(81, 9.5) "
        "wins, so with luck the spread of records is about ±11.5, roughly MLB's recent spread. Each season is Binomial(162). "
        "Six teams per league qualify: three division winners and three wild cards. Then we add the verified wins to one team "
        "of a given talent. A berth is valued at $15M, $30M and $50M to the club after revenue sharing (48% of net local revenue "
        "is pooled). That covers the home playoff gate (a Wild Card series host keeps roughly $5-15M), plus the following "
        "season's lift in attendance, sponsorship and local media. An older estimate puts that lift at 20-30% of local revenue; "
        "a 2023 World Series run was put at $30-40M.",
        "",
        "| Team situation | Playoff odds today | Added by the verified wins (low / mid / high) | Expected $ at $15M / $30M / $50M per berth (mid wins) |",
        "|---|---|---|---|",
        *[f"| {name} | {v['base']:.0%} | {100 * v['gain'][0]:+.1f} / {100 * v['gain'][1]:+.1f} / {100 * v['gain'][2]:+.1f} pts | "
          f"${v['value']['15.0'][1]:.1f}M / ${v['value']['30.0'][1]:.1f}M / ${v['value']['50.0'][1]:.1f}M |"
          for name, v in D["playoffs"].items()],
        "",
        "For comparison, the original +2.4 claim would add "
        + ", ".join(f"{100 * g:+.1f} pts ({name.split(' (')[0].lower()})" for name, g in D["claimed_playoffs"].items())
        + " to playoff odds.",
        "",
        "### The whole league",
        "",
        "Wins are zero-sum: every game has one winner, so the league's 2,430 wins stay 2,430 whatever tools teams use.",
        "",
        f"- **One early adopter** (above): it gains about {D['wins'][1]:+.1f} wins a season, taken from the other 29 teams "
        "(about 0.05 wins each). That is the only case where the app's value shows up as wins.",
        "- **Every team adopts:** the edges cancel. Each team's plan improves, but so does its opponent's, and league-wide "
        "wins can't rise. Expected wins per team go back toward 81, and the value in wins shrinks toward zero. What remains "
        "is cost and time: a full game plan costs about $0.019 in model calls, about $3 per team-season (Phase 8), against "
        "hours of staff preparation. That is a real saving, but it is measured in staff hours, not wins.",
        f"- **What a team might pay (licensing view, kept modest):** a buyer would pay only a slice of the value it expects, "
        f"because rivals can copy the methods (they are public), and its own analysts could rebuild much of this. At "
        f"{LICENSE_SHARE[0]:.0%}-{LICENSE_SHARE[1]:.0%} of the expected first-mover value, that is roughly "
        f"${D['license'][0]:.1f}M-${D['license'][1]:.1f}M per team per season, falling as adoption spreads. This is an "
        "illustration, not a market quote.",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    if "--dollars" in sys.argv:          # re-price from the saved results without re-running the checks
        sys.stdout.reconfigure(encoding="utf-8")
        saved = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        dollars(saved)
        write(saved)
    else:
        main()
