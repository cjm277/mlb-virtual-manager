"""The win model and the lineup it rates best (no LLM).

Each hitter's plate appearances are valued with the inputs that best predicted 2026 results out of sample
(scripts/value_model_search.py, data/lineup_params.json): his xwOBA regressed toward league average, his own
platoon split vs this starter's hand (regressed toward the league split), and the starter's wOBA allowed. Plate
appearances per batting-order slot, the starter's usual depth, and a league-average bullpen turn that into
expected runs; Pythagenpat turns runs into win probability.

best_lineup() picks the nine, their positions and the order that maximize expected runs against the opposing
starter. Only players who have started at a position this season (or whose listed position it is) can play
it. A hitter past the rest-day threshold costs nothing extra today (2026 data shows no same-day fatigue cost;
scripts/lineup_params.py), so he is rested only on a day when sitting him costs at most REST_MAX_COST
win-probability points: the cheapest days, chosen by the numbers.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache

from backend import config, db
from backend.engine import roster, workload
from backend.engine.hitting import batter_split, season_line
from backend.engine.matchups import batting_side
from backend.engine.pitching import pitcher_split

SLOT_PA = {1: 4.63, 2: 4.53, 3: 4.42, 4: 4.32, 5: 4.22, 6: 4.11, 7: 3.99, 8: 3.87, 9: 3.75}   # 2026 league
POSITIONS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]
WOBA_SCALE = 1.20
PYTH = 0.287
HOME_LOGIT = 0.16
REST_MAX_COST = 0.0025       # rest a tired hitter only if it costs at most 0.25 win-probability points today
PLATOON_PRIOR_PA = 400       # a hitter's own platoon split is trusted halfway at this many PA vs that hand


@lru_cache(maxsize=1)
def params() -> dict:
    p = json.loads((config.REPO_ROOT / "data" / "lineup_params.json").read_text(encoding="utf-8"))
    return p["value_model"] | {"calibration": p.get("season_value_slope", 1.0)}


@lru_cache(maxsize=1)
def league() -> dict:
    lw = db.one("SELECT SUM(woba_num) * 1.0 / SUM(woba_den) w, SUM(xwoba_num) * 1.0 / SUM(woba_den) x "
                "FROM statcast_batter_season WHERE season = 2025")
    rpg = db.one("SELECT SUM(home_score + away_score) * 1.0 / (2 * COUNT(*)) r FROM games")["r"]
    sp = db.one("""SELECT AVG(p.bf) sbf, AVG(t.pa) tpa FROM pitching_lines p
                   JOIN (SELECT game_pk, team_id, SUM(bf) pa FROM pitching_lines GROUP BY 1, 2) t
                     ON t.game_pk = p.game_pk AND t.team_id = p.team_id WHERE p.is_starter = 1""")
    rows = db.rows("""SELECT p.bat_side, s.p_throws, SUM(s.woba_num) num, SUM(s.woba_den) den
                      FROM statcast_batter_season s JOIN players p ON p.player_id = s.batter_id
                      WHERE s.season = 2025 GROUP BY 1, 2""")
    edge = [0.0, 0.0]; no_edge = [0.0, 0.0]
    for r in rows:
        if r["den"]:
            t = edge if (r["bat_side"] == "S" or (r["bat_side"] and r["bat_side"] != r["p_throws"])) else no_edge
            t[0] += r["num"]; t[1] += r["den"]
    overall = (edge[0] + no_edge[0]) / (edge[1] + no_edge[1])
    return {"woba": lw["w"], "xwoba": lw["x"], "rpg": rpg or 4.5, "starter_bf": sp["sbf"] or 21.4,
            "team_pa": sp["tpa"] or 37.8, "platoon_edge": edge[0] / edge[1] - overall,
            "platoon_no_edge": no_edge[0] / no_edge[1] - overall}


def _shrink(v: float | None, n: float, k: float, to: float) -> float:
    return to if v is None else (v * n + to * k) / (n + k)


@lru_cache(maxsize=None)
def hitter_value(pid: int, d: str) -> float:
    """His expected wOBA against a league-average pitcher, before platoon."""
    p, lg = params(), league()
    r = batter_split(pid, d, keys=["woba", "xwoba"])
    n = r["sample"]["pa"]
    w = _shrink(r["woba"], n, p["k_hitter"], lg["woba"])
    x = _shrink(r["xwoba"], n, p["k_hitter"], lg["xwoba"]) - lg["xwoba"] + lg["woba"]
    return {"woba": w, "xwoba": x, "blend": (w + x) / 2}[p["hitter"]]


@lru_cache(maxsize=None)
def platoon(pid: int, d: str, throws: str) -> float:
    """His platoon adjustment vs a pitcher who throws `throws`."""
    lg = league()
    bats = (roster.player_info(pid) or {}).get("bat_side")
    has_edge = batting_side(bats, throws) != throws
    lg_adj = lg["platoon_edge"] if has_edge else lg["platoon_no_edge"]
    if params()["platoon"] != "own":
        return lg_adj
    overall = batter_split(pid, d, keys=["woba"])
    split = batter_split(pid, d, throws, keys=["woba"])
    if overall["woba"] is None or split["woba"] is None:
        return lg_adj
    n = split["sample"]["pa"]
    return ((split["woba"] - overall["woba"]) * n + lg_adj * PLATOON_PRIOR_PA) / (n + PLATOON_PRIOR_PA)


@lru_cache(maxsize=None)
def starter_quality(pid: int, d: str) -> float:
    """wOBA (or xwOBA) he allows, regressed toward league."""
    p, lg = params(), league()
    r = pitcher_split(pid, d)
    n = r["sample"]["batters_faced"]
    w = _shrink(r["woba"], n, p["k_pitcher"], lg["woba"])
    x = _shrink(r["xwoba"], n, p["k_pitcher"], lg["xwoba"]) - lg["xwoba"] + lg["woba"]
    return {"woba": w, "xwoba": x, "blend": (w + x) / 2}[p["pitcher"]]


@lru_cache(maxsize=None)
def starter_depth(pid: int, d: str) -> float:
    """Batters he usually faces per start, regressed toward league (trusted halfway at 5 starts)."""
    r = db.one("SELECT COUNT(*) n, AVG(bf) bf FROM pitching_lines WHERE player_id = ? AND is_starter = 1 AND game_date < ?",
               pid, d)
    n = r["n"] or 0
    return ((r["bf"] or 0) * n + league()["starter_bf"] * 5) / (n + 5)


def pa_runs(pid: int, d: str, sp_id: int) -> float:
    """Runs above average per plate appearance for this hitter in this game (vs the starter, then the bullpen)."""
    lg = league()
    throws = (roster.player_info(sp_id) or {}).get("pitch_hand") or "R"
    share = min(starter_depth(sp_id, d) / lg["team_pa"], 0.9)
    h = hitter_value(pid, d)
    vs_sp = h + platoon(pid, d, throws) + starter_quality(sp_id, d) - lg["woba"]
    above = share * (vs_sp - lg["woba"]) + (1 - share) * (h - lg["woba"])
    return params()["calibration"] * above / WOBA_SCALE


def expected_runs(lineup: list[tuple[int, int]], d: str, sp_id: int) -> float:
    """lineup = [(slot, player_id), ...] -> expected runs against this starter and a league-average bullpen."""
    return max(league()["rpg"] + sum(SLOT_PA[s] * pa_runs(pid, d, sp_id) for s, pid in lineup), 0.5)


def win_prob(rs: float, ra: float, home: bool | None = None) -> float:
    x = (rs + ra) ** PYTH
    p = rs ** x / (rs ** x + ra ** x)
    z = math.log(p / (1 - p)) + (0 if home is None else HOME_LOGIT if home else -HOME_LOGIT)
    return 1 / (1 + math.exp(-z))


# ---------------------------------------------------------------------------
# The best lineup
# ---------------------------------------------------------------------------

def eligible_positions(pid: int, d: str) -> set[str]:
    started = season_line(pid, d)["starts_by_position"]
    listed = (roster.player_info(pid) or {}).get("primary_position")
    pos = {p for p, n in started.items() if n >= 1} | ({listed} if listed in POSITIONS else set())
    if listed in ("LF", "CF", "RF", "OF"):
        pos |= {"LF", "RF"} if listed != "CF" else {"CF", "LF", "RF"}
    return (pos - {"P"}) | {"DH"}


def _assign(values: dict[int, float], elig: dict[int, set[str]]) -> tuple[float, dict[str, int]] | None:
    """Best total value filling each position once (exact search over positions, memoized on who is used)."""
    order = POSITIONS
    players = list(values)

    @lru_cache(maxsize=None)
    def best(i: int, used: frozenset) -> tuple[float, tuple]:
        if i == len(order):
            return 0.0, ()
        top = (-math.inf, ())
        for pid in players:
            if pid not in used and order[i] in elig[pid]:
                v, rest = best(i + 1, used | {pid})
                if v + values[pid] > top[0]:
                    top = (v + values[pid], ((order[i], pid),) + rest)
        return top

    total, picks = best(0, frozenset())
    return None if total == -math.inf else (total, dict(picks))


def _order(d: str, sp_id: int, nine: dict[str, int]) -> list[tuple[int, int, str]]:
    """Best hitters bat most: sort by runs per PA, top of the order first."""
    ranked = sorted(nine.items(), key=lambda kv: -pa_runs(kv[1], d, sp_id))
    return [(slot, pid, pos) for slot, (pos, pid) in enumerate(ranked, start=1)]


def best_lineup(team_id: int, d: str, sp_id: int, unavailable: set[int] = frozenset(), home: bool | None = None) -> dict:
    """The lineup the win model rates best against starter sp_id, with every number behind it."""
    hitters = [r for r in roster.active_roster(team_id, d) if not roster.is_pitcher(r) and r["player_id"] not in unavailable]
    values = {r["player_id"]: pa_runs(r["player_id"], d, sp_id) for r in hitters}
    elig = {r["player_id"]: eligible_positions(r["player_id"], d) for r in hitters}
    tired = {r["player_id"]: workload.rest_check(team_id, r["player_id"], d, r["position"]) for r in hitters}

    def build(excluded: set[int]) -> tuple[float, list[tuple[int, int, str]]] | None:
        v = {p: x for p, x in values.items() if p not in excluded}
        got = _assign(v, {p: elig[p] for p in v})
        if not got:
            return None
        order = _order(d, sp_id, got[1])
        return expected_runs([(s, p) for s, p, _ in order], d, sp_id), order

    full = build(set())
    if full is None:
        raise ValueError("No legal lineup: not enough available hitters to cover every position.")
    runs, order = full
    rested, rest_notes = set(), []
    lg_runs = league()["rpg"]
    for pid in [p for _, p, _ in order if tired[p]["rest_suggested"]]:
        alt = build(rested | {pid})
        cost = (win_prob(runs, lg_runs, home) - win_prob(alt[0], lg_runs, home)) if alt else 1.0
        name = roster.player_name(pid)
        if alt and cost <= REST_MAX_COST:
            rested.add(pid)
            runs, order = alt
            rest_notes.append(f"{name}: resting him today costs {100 * cost:.2f} win-probability points, at most "
                              f"{100 * REST_MAX_COST:.2f}, so today is a good rest day ({tired[pid]['rest_note']})")
        else:
            rest_notes.append(f"{name}: plays; resting him today would cost {100 * cost:.2f} win-probability points "
                              f"(rest only on days costing {100 * REST_MAX_COST:.2f} or less). {tired[pid]['rest_note']}")
    names = {r["player_id"]: r["full_name"] for r in hitters}
    bats = {r["player_id"]: r["bat_side"] for r in hitters}
    in_lineup = {p for _, p, _ in order}
    return {
        "opposing_starter_id": sp_id,
        "lineup": [{"slot": s, "player_id": p, "name": names[p], "position": pos, "bats": bats[p],
                    "runs_per_pa_vs_avg": round(values[p], 4)} for s, p, pos in order],
        "expected_runs": round(runs, 2),
        "rest_decisions": rest_notes,
        "bench_ranked": [{"player_id": p, "name": names[p], "runs_per_pa_vs_avg": round(values[p], 4),
                          "positions": sorted(elig[p] - {"DH"})}
                         for p in sorted(values, key=lambda p: -values[p]) if p not in in_lineup],
        "how": ("Win model: hitter xwOBA regressed toward league, his own platoon split vs this starter's hand, the "
                "starter's quality and usual depth, PA by batting-order slot; maximized over legal positions."),
    }
