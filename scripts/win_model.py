"""Win-impact analysis, the math. Run through scripts/win_impact.py.

The question: given only what was known before first pitch, is the staff's plan analytically more likely to win
than the plan the real manager used? Both plans go through the same analytic win model:
  lineup and starting pitchers -> expected runs scored and allowed -> win probability (Pythagenpat)
with everything else held fixed (the opponent's lineup and starter, both bullpens, home field). The difference
is the plan's edge in win probability. Game results are used only in the appendix, to check the model's
probabilities are realistic and whether its inputs carry real information.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np

from backend import db
from backend.engine.hitting import batter_split
from backend.engine.matchups import batting_side, matchup
from backend.engine.pitching import pitcher_split
from backend.engine.roster import player_info

ROOT = Path(__file__).resolve().parents[1]
SAVE = ROOT / "evidence" / "logs" / "win_impact"
PLANS = SAVE / "plans"
FEATURES = SAVE / "features.json"
REPORT = ROOT / "evidence" / "tests" / "win_impact.md"
NOTES = ROOT / "evidence" / "tests" / "win_impact_interpretation.md"     # hand-written; appended
BOOT = 1000
SEED = 409

# League plate appearances per game by batting-order slot (2026 box scores): the top of the order bats more.
SLOT_PA = {1: 4.63, 2: 4.53, 3: 4.42, 4: 4.32, 5: 4.22, 6: 4.11, 7: 3.99, 8: 3.87, 9: 3.75}


# ---------------------------------------------------------------------------
# Player values (cached; all "as of the day before the game")
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def hitter(pid: int, d: str) -> tuple[float | None, int]:
    r = batter_split(pid, d, keys=["woba"])
    return r["woba"], r["sample"]["pa"]


@lru_cache(maxsize=None)
def pitcher(pid: int, d: str) -> tuple[float | None, int]:
    r = pitcher_split(pid, d)
    return r["woba"], r["sample"]["batters_faced"]


@lru_cache(maxsize=None)
def hand(pid: int) -> tuple[str | None, str | None]:
    p = player_info(pid) or {}
    return p.get("bat_side"), p.get("pitch_hand")


@lru_cache(maxsize=None)
def matchup_x(batter: int, sp: int, d: str) -> float:
    return matchup(batter, sp, d)["expected_xwoba"]


@lru_cache(maxsize=1)
def platoon_split() -> tuple[float, float]:
    """League wOBA with and without the platoon edge, from 2025 (so no 2026 game is used to set it)."""
    rows = db.rows("""SELECT p.bat_side, s.p_throws, SUM(s.woba_num) num, SUM(s.woba_den) den
                      FROM statcast_batter_season s JOIN players p ON p.player_id = s.batter_id
                      WHERE s.season = 2025 GROUP BY 1, 2""")
    adv = [0.0, 0.0]; same = [0.0, 0.0]
    for r in rows:
        if not r["den"]:
            continue
        has_edge = r["bat_side"] == "S" or (r["bat_side"] and r["bat_side"] != r["p_throws"])
        t = adv if has_edge else same
        t[0] += r["num"]; t[1] += r["den"]
    a, s = adv[0] / adv[1], same[0] / same[1]
    overall = (adv[0] + same[0]) / (adv[1] + same[1])
    return a - overall, s - overall          # e.g. +0.008 with the edge, -0.012 without


# ---------------------------------------------------------------------------
# Stage 1: features for every game
# ---------------------------------------------------------------------------

def side_record(game_pk: int, team_id: int, d: str, opp_sp: int) -> dict:
    lineup = []
    for r in db.rows("SELECT player_id, lineup_slot FROM batting_lines WHERE game_pk = ? AND team_id = ? AND is_starter = 1 "
                     "ORDER BY lineup_slot", game_pk, team_id):
        lineup.append(hitter_entry(r["player_id"], r["lineup_slot"], d, opp_sp))
    sp = db.one("SELECT player_id FROM pitching_lines WHERE game_pk = ? AND team_id = ? AND is_starter = 1",
                game_pk, team_id)["player_id"]
    return {"lineup": lineup, "sp": pitcher_entry(sp, d)}


def hitter_entry(pid: int, slot: int, d: str, opp_sp: int) -> dict:
    w, n = hitter(pid, d)
    bats = hand(pid)[0]
    edge = batting_side(bats, hand(opp_sp)[1] or "R") != (hand(opp_sp)[1] or "R")
    return {"pid": pid, "slot": slot, "woba": w, "n": n, "edge": edge, "mx": matchup_x(pid, opp_sp, d)}


def pitcher_entry(pid: int, d: str) -> dict:
    w, n = pitcher(pid, d)
    return {"pid": pid, "woba": w, "n": n, "throws": hand(pid)[1]}


def build_features() -> None:
    games = db.rows("SELECT game_pk, game_date, home_team_id, away_team_id, home_score, away_score FROM games "
                    "ORDER BY game_date, game_pk")
    out = []
    for i, g in enumerate(games):
        d = g["game_date"]
        sps = {r["team_id"]: r["player_id"] for r in db.rows(
            "SELECT team_id, player_id FROM pitching_lines WHERE game_pk = ? AND is_starter = 1", g["game_pk"])}
        h, a = g["home_team_id"], g["away_team_id"]
        out.append({"game_pk": g["game_pk"], "date": d, "home_id": h, "away_id": a,
                    "home_win": int(g["home_score"] > g["away_score"]),
                    "home": side_record(g["game_pk"], h, d, sps[a]), "away": side_record(g["game_pk"], a, d, sps[h])})
        if i % 200 == 0:
            print(f"  {i}/{len(games)} {d}", flush=True)
    SAVE.mkdir(parents=True, exist_ok=True)
    FEATURES.write_text(json.dumps(out), encoding="utf-8")
    print(f"Wrote {len(out)} games to {FEATURES}")


# ---------------------------------------------------------------------------
# Lineup and starter values
# ---------------------------------------------------------------------------

LEAGUE = 0.320     # replaced at load time by the 2025 league wOBA


def shrink(w: float | None, n: float, k: float) -> float:
    """Regress a rate toward league average: a hitter with k plate appearances is trusted halfway."""
    return LEAGUE if w is None else (w * n + LEAGUE * k) / (n + k)


def lineup_value(lineup: list[dict], k: float, metric: str) -> float:
    adv, same = platoon_split()
    tot = wsum = 0.0
    for e in lineup:
        if metric == "matchup":
            v = e["mx"]
        else:
            v = shrink(e["woba"], e["n"], k) + (adv if e["edge"] else same)
        tot += SLOT_PA[e["slot"]] * v
        wsum += SLOT_PA[e["slot"]]
    return tot / wsum


def starter_value(sp: dict, k: float) -> float:
    return shrink(sp["woba"], sp["n"], k)


def design(rows: list[dict], metric: str, kh: float, kp: float) -> np.ndarray:
    """Home-team point of view, in units of .010 wOBA: [1, lineup edge, starter edge]."""
    X = []
    for r in rows:
        dl = lineup_value(r["home"]["lineup"], kh, metric) - lineup_value(r["away"]["lineup"], kh, metric)
        if metric == "matchup":         # the matchup score already blends the opposing starter in
            X.append([1.0, 100 * dl])
        else:
            ds = starter_value(r["away"]["sp"], kp) - starter_value(r["home"]["sp"], kp)
            X.append([1.0, 100 * dl, 100 * ds])
    return np.array(X)


# ---------------------------------------------------------------------------
# Logistic regression (IRLS) and scores
# ---------------------------------------------------------------------------

def fit(X: np.ndarray, y: np.ndarray, ridge: float = 1e-6) -> tuple[np.ndarray, np.ndarray]:
    b = np.zeros(X.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ b))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None]) + ridge * np.eye(len(b))
        step = np.linalg.solve(H, X.T @ (y - p))
        b += step
        if np.abs(step).max() < 1e-10:
            break
    p = 1 / (1 + np.exp(-X @ b))
    cov = np.linalg.inv(X.T @ (X * (p * (1 - p))[:, None]))
    return b, cov


def predict(X: np.ndarray, b: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-X @ b))


def scores(y: np.ndarray, p: np.ndarray) -> dict:
    eps = 1e-12
    ll = -np.mean(y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))
    brier = np.mean((p - y) ** 2)
    order = np.argsort(p)
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    auc = (ranks[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum())
    return {"log_loss": float(ll), "brier": float(brier), "auc": float(auc)}


# ---------------------------------------------------------------------------
# Stage 2: score the staff's plans against the real choices
# ---------------------------------------------------------------------------

def plan_cases() -> list[dict]:
    feats = {r["game_pk"]: r for r in json.loads(FEATURES.read_text(encoding="utf-8"))}
    cases = []
    for run in sorted(PLANS.iterdir()):
        f = run / "plan.json"
        if not f.exists():
            continue
        plan = json.loads(f.read_text(encoding="utf-8"))
        s = plan["sections"]
        if not s.get("lineup_card") or not s.get("pitching_plan"):
            continue
        gc = plan["game"]
        g = feats[gc["game_pk"]]
        us = "home" if g["home_id"] == gc["team_id"] else "away"
        them = "away" if us == "home" else "home"
        d = g["date"]
        opp_sp = g[them]["sp"]["pid"]
        our_lineup = [hitter_entry(x["player_id"], x["slot"], d, opp_sp) for x in s["lineup_card"]["lineup"]]
        our_sp = s["pitching_plan"]["starter"]["player_id"]
        # The opponent's real lineup, re-scored against the starter we chose (platoon edge, matchup).
        opp_vs_plan_sp = [hitter_entry(e["pid"], e["slot"], d, our_sp) for e in g[them]["lineup"]]
        real_ids = {e["pid"] for e in g[us]["lineup"]}
        appeared = {r["player_id"] for r in db.rows("SELECT player_id FROM batting_lines WHERE game_pk = ? AND team_id = ?",
                                                    gc["game_pk"], gc["team_id"])}
        nxt = db.one("SELECT game_pk FROM batting_lines WHERE team_id = ? AND game_date > ? ORDER BY game_date LIMIT 1",
                     gc["team_id"], d)
        next_ids = ({r["player_id"] for r in db.rows("SELECT player_id FROM batting_lines WHERE game_pk = ? AND team_id = ?",
                                                     nxt["game_pk"], gc["team_id"])} if nxt else set())
        # A player we started who didn't play at all that day or in the next game may have been hurt.
        maybe_hurt = [x["player_id"] for x in s["lineup_card"]["lineup"]
                      if x["player_id"] not in appeared and x["player_id"] not in next_ids]
        nxt_start = db.one("SELECT MIN(game_date) d FROM pitching_lines WHERE player_id = ? AND is_starter = 1 AND game_date > ?",
                           our_sp, d)["d"]
        # Our starter differs from the real one, but he really did start in the next two days: we moved him up a turn.
        moved_up = our_sp != g[us]["sp"]["pid"] and nxt_start is not None and (
            datetime.fromisoformat(nxt_start) - datetime.fromisoformat(d)).days <= 2
        rest = {x["player_id"] for x in (s.get("medical_report") or {}).get("statuses", []) if x["status"] == "rest_suggested"}
        plan_ids = {e["pid"] for e in our_lineup}
        cases.append({
            "added": [e for e in our_lineup if e["pid"] not in real_ids],
            "benched": [dict(e, rest=e["pid"] in rest) for e in g[us]["lineup"] if e["pid"] not in plan_ids],
            "run": run.name, "date": d, "team_id": gc["team_id"], "home": us == "home", "status": plan["status"],
            "real": {"lineup": g[us]["lineup"], "sp": g[us]["sp"]}, "opp_real": g[them]["lineup"],
            "plan": {"lineup": our_lineup, "sp": pitcher_entry(our_sp, d)}, "opp_vs_plan_sp": opp_vs_plan_sp,
            "opp_sp": g[them]["sp"],
            "same_sp": our_sp == g[us]["sp"]["pid"], "overlap": len(real_ids & {e["pid"] for e in our_lineup}),
            "maybe_hurt": maybe_hurt, "moved_up": moved_up,
        })
    return cases


# ---------------------------------------------------------------------------
# The analytic win model: lineup and pitchers -> expected runs -> win probability
# ---------------------------------------------------------------------------

LG_RPG = 4.48          # league runs per team per game (set from the data at load time)
LG_XWOBA = 0.318       # league xwOBA, to put the matchup lens on the wOBA scale (set at load time)
STARTER_BF = 21.4      # league batters faced per start (set at load time)
TEAM_PA = 37.8         # league plate appearances per team per game (set at load time)
HOME_LOGIT = 0.16      # standard home-field edge (about 54%); identical for both plans of a game


@dataclass(frozen=True)
class Params:
    scale: float = 1.20     # wOBA scale: runs per PA = (wOBA - league) / scale
    kh: float = 200         # a hitter's wOBA is trusted halfway at this many PA
    kp: float = 400         # a pitcher's wOBA allowed is trusted halfway at this many batters faced
    pyth: float = 0.287     # Pythagenpat exponent


@lru_cache(maxsize=None)
def starter_depth(pid: int, d: str) -> float:
    """Batters this starter usually faces per start, regressed toward league (trusted halfway at 5 starts)."""
    r = db.one("SELECT COUNT(*) n, AVG(bf) bf FROM pitching_lines WHERE player_id = ? AND is_starter = 1 AND game_date < ?",
               pid, d)
    n = r["n"] or 0
    return ((r["bf"] or 0) * n + STARTER_BF * 5) / (n + 5)


def pa_vs_starter(e: dict, sp: dict, P: Params, lens: str) -> float:
    """Expected wOBA of one hitter's plate appearances against this starter."""
    if lens == "matchup":                       # the app's engine: hitter vs this starter's pitch mix
        return e["mx"] - LG_XWOBA + LEAGUE
    adv, same = platoon_split()
    return (shrink(e["woba"], e["n"], P.kh) + (adv if e["edge"] else same)
            + shrink(sp["woba"], sp["n"], P.kp) - LEAGUE)


def expected_runs(lineup: list[dict], opp_sp: dict, d: str, P: Params, lens: str) -> float:
    """Runs this lineup is expected to score: each slot's plate appearances, split between the opposing starter
    (for the share of the game he usually pitches) and a league-average bullpen."""
    share = min(starter_depth(opp_sp["pid"], d) / TEAM_PA, 0.9)
    above = 0.0
    for e in lineup:
        vs_sp = pa_vs_starter(e, opp_sp, P, lens)
        vs_pen = shrink(e["woba"], e["n"], P.kh)
        above += SLOT_PA[e["slot"]] * (share * (vs_sp - LEAGUE) + (1 - share) * (vs_pen - LEAGUE))
    return max(LG_RPG + above / P.scale, 0.5)


def win_prob(rs: float, ra: float, home: bool, P: Params) -> float:
    x = (rs + ra) ** P.pyth
    p = rs ** x / (rs ** x + ra ** x)
    z = math.log(p / (1 - p)) + (HOME_LOGIT if home else -HOME_LOGIT)
    return 1 / (1 + math.exp(-z))


def case_prob(c: dict, lineup: str, sp: str, P: Params, lens: str) -> float:
    """P(our team wins) with our lineup and our starter each taken from 'real' or 'plan'."""
    our_sp = c[sp]["sp"]
    opp_lineup = c["opp_real"] if sp == "real" else c["opp_vs_plan_sp"]
    rs = expected_runs(c[lineup]["lineup"], c["opp_sp"], c["date"], P, lens)
    ra = expected_runs(opp_lineup, our_sp, c["date"], P, lens)
    return win_prob(rs, ra, c["home"], P)


def edges(cases: list[dict], P: Params, lens: str) -> dict[str, np.ndarray]:
    real = np.array([case_prob(c, "real", "real", P, lens) for c in cases])
    plan = np.array([case_prob(c, "plan", "plan", P, lens) for c in cases])
    return {"real": real, "plan": plan, "both": plan - real,
            "lineup": np.array([case_prob(c, "plan", "real", P, lens) for c in cases]) - real,
            "starter": np.array([case_prob(c, "real", "plan", P, lens) for c in cases]) - real}


def boot_ci(x: np.ndarray, rng: np.random.Generator) -> list[float]:
    means = [x[rng.integers(0, len(x), len(x))].mean() for _ in range(BOOT)]
    return np.percentile(means, [2.5, 97.5]).tolist()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def pct(x: float) -> str:
    return f"{100 * x:+.2f} pts"


def load_constants() -> None:
    global LEAGUE, LG_RPG, LG_XWOBA, STARTER_BF, TEAM_PA
    LEAGUE = float(db.one("SELECT SUM(woba_num) * 1.0 / SUM(woba_den) w FROM statcast_batter_season WHERE season = 2025")["w"])
    LG_XWOBA = float(db.one("SELECT SUM(xwoba_num) * 1.0 / SUM(woba_den) w FROM statcast_batter_season WHERE season = 2025")["w"])
    LG_RPG = float(db.one("SELECT SUM(home_score + away_score) * 1.0 / (2 * COUNT(*)) r FROM games")["r"])
    r = db.one("""SELECT AVG(p.bf) sbf, AVG(t.pa) tpa FROM pitching_lines p
                  JOIN (SELECT game_pk, team_id, SUM(bf) pa FROM pitching_lines GROUP BY 1, 2) t
                    ON t.game_pk = p.game_pk AND t.team_id = p.team_id WHERE p.is_starter = 1""")
    STARTER_BF, TEAM_PA = float(r["sbf"]), float(r["tpa"])


def write_report() -> None:
    load_constants()
    rows = json.loads(FEATURES.read_text(encoding="utf-8"))
    cases = plan_cases()
    rng = np.random.default_rng(SEED)
    base = Params()
    out: dict = {"n_cases": len(cases), "constants": {"league_woba_2025": LEAGUE, "league_xwoba_2025": LG_XWOBA,
                 "runs_per_game": LG_RPG, "starter_bf": STARTER_BF, "team_pa": TEAM_PA, "platoon": platoon_split(),
                 "params": base.__dict__}, "lenses": {}}

    subsets = {
        "All plans": np.ones(len(cases), bool),
        "Excluding plans that started a possibly hurt player": np.array([not c["maybe_hurt"] for c in cases]),
        "Same starting pitcher as the real team": np.array([c["same_sp"] for c in cases]),
        "Plans the Manager approved": np.array([c["status"] == "approved" for c in cases]),
        "Plans with no rest-day benching": np.array([not any(x["rest"] for x in c["benched"]) for c in cases]),
        "Our starter = the real team's next starter, moved up": np.array([c["moved_up"] for c in cases]),
        "Our starter differs, and was not the next starter": np.array([not c["same_sp"] and not c["moved_up"] for c in cases]),
    }
    grid = [replace(base, scale=s_, kh=kh, kp=kp) for s_ in (1.1, 1.2, 1.3) for kh in (100, 200, 800) for kp in (200, 400, 800)]
    for lens in ("results", "matchup"):
        e = edges(cases, base, lens)
        sens = [float(edges(cases, P, lens)["both"].mean()) for P in grid]
        out["lenses"][lens] = {
            "real_mean": float(e["real"].mean()), "plan_mean": float(e["plan"].mean()),
            **{k: float(e[k].mean()) for k in ("both", "lineup", "starter")},
            "ci": {k: boot_ci(e[k], rng) for k in ("both", "lineup", "starter")},
            "sensitivity": [min(sens), max(sens)],
            "better": float((e["both"] > 0.0005).mean()), "worse": float((e["both"] < -0.0005).mean()),
            "subsets": {n: {"n": int(m.sum()), "both": float(e["both"][m].mean()), "lineup": float(e["lineup"][m].mean())}
                        for n, m in subsets.items()},
            "per_game": [{"run": c["run"], "real": float(r_), "plan": float(p_)} for c, r_, p_ in zip(cases, e["real"], e["plan"])],
        }

    # Anatomy of the lineup changes, on the season-stats lens.
    adv, same = platoon_split()
    val = lambda x: shrink(x["woba"], x["n"], base.kh) + (adv if x["edge"] else same)  # noqa: E731
    added = [x for c in cases for x in c["added"]]
    benched = [x for c in cases for x in c["benched"]]
    rest = [x for x in benched if x["rest"]]
    other = [x for x in benched if not x["rest"]]
    mean = lambda xs, f: float(np.mean([f(x) for x in xs])) if xs else float("nan")  # noqa: E731
    out["swaps"] = {"per_game": len(added) / len(cases), "rest_share": len(rest) / max(len(benched), 1),
                    "added_value": mean(added, val), "benched_value": mean(benched, val),
                    "rest_value": mean(rest, val), "other_value": mean(other, val),
                    "added_edge": mean(added, lambda x: x["edge"]), "benched_edge": mean(benched, lambda x: x["edge"]),
                    "added_mx": mean(added, lambda x: x["mx"]), "benched_mx": mean(benched, lambda x: x["mx"]),
                    "added_n": mean(added, lambda x: x["n"]), "benched_n": mean(benched, lambda x: x["n"])}
    out["sample"] = {"overlap": float(np.mean([c["overlap"] for c in cases])),
                     "moved_up": sum(c["moved_up"] for c in cases),
                     "same_sp": float(np.mean([c["same_sp"] for c in cases])),
                     "maybe_hurt": sum(bool(c["maybe_hurt"]) for c in cases),
                     "approved": sum(c["status"] == "approved" for c in cases)}

    # Appendix A: are the model's probabilities realistic? Every 2026 game, real lineups and starters.
    home_p = np.array([win_prob(expected_runs(g["home"]["lineup"], g["away"]["sp"], g["date"], base, "results"),
                                expected_runs(g["away"]["lineup"], g["home"]["sp"], g["date"], base, "results"),
                                True, base) for g in rows])
    y = np.array([g["home_win"] for g in rows], float)
    cuts = np.quantile(home_p, [0, .2, .4, .6, .8, 1])
    calib = []
    for lo, hi in zip(cuts[:-1], cuts[1:]):
        m = (home_p >= lo) & (home_p <= hi)
        calib.append((float(home_p[m].mean()), float(y[m].mean()), int(m.sum())))
    out["calibration"] = calib
    out["calibration_scores"] = {"model": scores(y, home_p), "flat_54": scores(y, np.full(len(y), 0.54))}

    # Appendix B: does each input carry real information? Logistic fit of results on the three edges.
    Xr, Xm = design(rows, "results", base.kh, base.kp), design(rows, "matchup", 0, 0)
    Xc = np.column_stack([Xr, Xm[:, 1]])
    bc, covc = fit(Xc, y)
    out["inputs"] = {"coef": bc.tolist(), "z": (bc / np.sqrt(np.diag(covc))).tolist(),
                     "corr_matchup_starter": float(np.corrcoef(Xr[:, 2], Xm[:, 1])[0, 1])}

    (SAVE / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    text = render(out)
    if NOTES.exists():
        text += "\n" + NOTES.read_text(encoding="utf-8")
    REPORT.write_text(text, encoding="utf-8")
    print(text)


def render(o: dict) -> str:
    R, M, s, w, k = o["lenses"]["results"], o["lenses"]["matchup"], o["sample"], o["swaps"], o["constants"]
    wins = lambda x: f"{162 * x:+.1f}"  # noqa: E731
    rng_ = lambda ci: f"{pct(ci[0])} to {pct(ci[1])}"  # noqa: E731
    L = [
        "# Win model: is the staff's plan more likely to win than the manager's?",
        "",
        f"Generated {datetime.now():%Y-%m-%d %H:%M} by `scripts/win_impact.py`. Per-game numbers: "
        "`evidence/logs/win_impact/results.json`; the plans and their audit trails: `evidence/logs/win_impact/plans/`.",
        "",
        "**The question.** Given only what was known the day before the game, is the lineup and starting pitcher our "
        "staff chose analytically more likely to win than the lineup and starter the real manager chose? Both go "
        "through the same win model, with everything else held fixed: the opponent's real lineup and starter, both "
        "bullpens, and home field. Game results play no part in the comparison.",
        "",
        "## The win model",
        "",
        "1. **Each hitter's value:** his wOBA to date, regressed toward league average for small samples (trusted "
        f"halfway at {k['params']['kh']:.0f} PA), plus the league-typical platoon edge "
        f"({k['platoon'][0]:+.3f} with it, {k['platoon'][1]:+.3f} without; measured on 2025).",
        f"2. **Each starter's value:** his wOBA allowed to date, regressed the same way (halfway at {k['params']['kp']:.0f} "
        "batters faced), and how deep he usually pitches (batters faced per start, regressed to the league's "
        f"{k['starter_bf']:.1f}).",
        "3. **Plate appearances:** each batting-order slot gets its league-average share (4.63 for the leadoff hitter "
        "down to 3.75 for the ninth), so the batting order counts. Each hitter faces the opposing starter for the share "
        "of the game that starter usually pitches, then a league-average bullpen.",
        f"4. **Runs:** expected wOBA above league average is turned into runs with the standard wOBA scale "
        f"({k['params']['scale']}), around the league's {k['runs_per_game']:.2f} runs per team per game.",
        "5. **Win probability:** runs scored and allowed go through Pythagenpat, the standard runs-to-wins formula, plus "
        "a standard home-field edge (54%).",
        "",
        "Two sources of player value, reported side by side:",
        "- **Season stats (independent):** steps 1 and 2 as described. The app never optimizes these numbers directly, "
        "so this column is the fair test.",
        "- **The app's matchup engine (its own lens):** a hitter's plate appearances against the starter are valued by "
        "the app's expected xwOBA for that hitter against that starter's pitch mix. Everything else is the same.",
        "",
        "## Result",
        "",
        f"{o['n_cases']} games: 5 per team, spread from mid-April to the last day of the 2026 season. The full staff "
        f"built each plan exactly as the app does ({s['approved']} were approved by the Manager). Our starting nine "
        f"shared {s['overlap']:.1f} players with the manager's on average, and our starter matched his in "
        f"{s['same_sp']:.0%} of games.",
        "",
        "| Average per game | Season stats (independent) | App's matchup engine |",
        "|---|---|---|",
        f"| Win probability, manager's plan | {100 * R['real_mean']:.2f}% | {100 * M['real_mean']:.2f}% |",
        f"| Win probability, our plan | {100 * R['plan_mean']:.2f}% | {100 * M['plan_mean']:.2f}% |",
        f"| **Edge: lineup + starter** | **{pct(R['both'])}** | **{pct(M['both'])}** |",
        f"| 95% range (sampling) | {rng_(R['ci']['both'])} | {rng_(M['ci']['both'])} |",
        f"| Range across model assumptions | {rng_(R['sensitivity'])} | {rng_(M['sensitivity'])} |",
        f"| Edge from the lineup alone | {pct(R['lineup'])} ({rng_(R['ci']['lineup'])}) | {pct(M['lineup'])} ({rng_(M['ci']['lineup'])}) |",
        f"| Edge from the starter alone | {pct(R['starter'])} ({rng_(R['ci']['starter'])}) | {pct(M['starter'])} ({rng_(M['ci']['starter'])}) |",
        f"| **Wins per 162 games** | **{wins(R['both'])}** ({wins(R['ci']['both'][0])} to {wins(R['ci']['both'][1])}) | "
        f"**{wins(M['both'])}** ({wins(M['ci']['both'][0])} to {wins(M['ci']['both'][1])}) |",
        f"| Games where our plan is better / worse | {R['better']:.0%} / {R['worse']:.0%} | {M['better']:.0%} / {M['worse']:.0%} |",
        "",
        "\"95% range (sampling)\" is a bootstrap over the sampled games. \"Range across model assumptions\" re-runs the "
        "whole comparison under 27 settings: wOBA scale 1.1 / 1.2 / 1.3, hitter regression 100 / 200 / 800 PA, and "
        "pitcher regression 200 / 400 / 800 batters faced.",
        "",
        "## Where the plans differ",
        "",
        f"Our nine differed from the manager's by {w['per_game']:.1f} players per game.",
        "",
        "| | Hitters we started instead | Hitters of his we benched |",
        "|---|---|---|",
        f"| Season value (wOBA, regressed, with platoon edge) | {w['added_value']:.3f} | {w['benched_value']:.3f} |",
        f"| Had the platoon edge against the opposing starter | {w['added_edge']:.0%} | {w['benched_edge']:.0%} |",
        f"| App's matchup score against the opposing starter | {w['added_mx']:.3f} | {w['benched_mx']:.3f} |",
        f"| Plate appearances behind the numbers | {w['added_n']:.0f} | {w['benched_n']:.0f} |",
        "",
        f"{w['rest_share']:.0%} of the hitters we benched were sitting for a suggested rest day (season value "
        f"{w['rest_value']:.3f}); the others were benched for matchups (season value {w['other_value']:.3f}). A rest day "
        "gives up a little today on purpose. Its payoff, fresher hitters later, is outside a one-game model.",
        "",
        "## Robustness",
        "",
        "| Plans included | Plans | Season stats: lineup + starter | lineup only | Matchup engine: lineup + starter | lineup only |",
        "|---|---|---|---|---|---|",
        *[f"| {n} | {v['n']} | {pct(v['both'])} | {pct(v['lineup'])} | {pct(M['subsets'][n]['both'])} | "
          f"{pct(M['subsets'][n]['lineup'])} |" for n, v in R["subsets"].items()],
        "",
        f"\"Possibly hurt\": {s['maybe_hurt']} plans started a hitter who did not play at all that day or in the team's "
        "next game. The data only knows injured-list moves, not day-to-day knocks.",
        "",
        "## Appendix A: are the model's probabilities realistic?",
        "",
        "The model applied to every 2026 game with the real lineups and starters. Predicted home win probability vs how "
        "often the home team won, by fifth of predictions:",
        "",
        "| Model says (average) | Home team won | Games |",
        "|---|---|---|",
        *[f"| {a:.1%} | {b:.1%} | {n} |" for a, b, n in o["calibration"]],
        "",
        f"Brier score {o['calibration_scores']['model']['brier']:.4f} vs {o['calibration_scores']['flat_54']['brier']:.4f} "
        "for \"54% for every home team\". Baseball is close to a coin flip game by game, so realistic probabilities "
        "stay in a narrow band. That's why a 1-point edge per game is worth a meaningful number of wins over 162.",
        "",
        "## Appendix B: do the inputs carry real information?",
        "",
        "A logistic regression of 2026 results on the three edges at once (log-odds per .010; |z| above 2 means "
        "clearly not zero):",
        "",
        "| Input | Coefficient | z |",
        "|---|---|---|",
        f"| Home field | {o['inputs']['coef'][0]:.3f} | {o['inputs']['z'][0]:.1f} |",
        f"| Lineup edge, season stats | {o['inputs']['coef'][1]:.3f} | {o['inputs']['z'][1]:.1f} |",
        f"| Starter edge, season stats | {o['inputs']['coef'][2]:.3f} | {o['inputs']['z'][2]:.1f} |",
        f"| Matchup edge, the app's engine | {o['inputs']['coef'][3]:.3f} | {o['inputs']['z'][3]:.1f} |",
        "",
        f"Correlation between the matchup edge and the starter edge: {o['inputs']['corr_matchup_starter']:.2f}.",
        "",
    ]
    return "\n".join(L)
