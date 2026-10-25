"""The win model and the lineup it rates best (no LLM).

Each hitter's plate appearances are valued with the inputs that best predicted 2026 results out of sample
(scripts/projection_search.py, data/lineup_params.json "projection"). Marcel-style: each player's 2026-to-date
counts are pooled with his 2025 counts (2025 weighted 0.75), then regressed toward league average. That gives his
xwOBA, his own platoon split vs this starter's hand (regressed toward the league split), and the starter's wOBA
allowed. Plate appearances per batting-order slot, the starter's usual depth, and a league-average bullpen turn that
into expected runs; Pythagenpat turns runs into win probability. (Before the Marcel search the model used the app's
six-week 2025 fade instead; set_version("fade") restores it for comparisons.)

Defense (backend/engine/defense.py): each fielder's runs saved per game at his position (multi-year Outs Above
Average at that position, catcher framing), worth one run allowed per rated run (measured on 2026 games).

best_lineup() picks the nine, their positions and the order that maximize expected runs scored PLUS runs saved
on defense against the opposing starter. Only players who have started at a position this season (or whose listed position it is) can play
it. A hitter past the rest-day threshold costs nothing extra today (2026 data shows no same-day fatigue cost;
scripts/lineup_params.py), so he is rested only on a day when sitting him costs at most REST_MAX_COST
win-probability points: the cheapest days, chosen by the numbers.

Catcher workload: a catcher who caught CATCHER_MAX_STARTS of his team's last CATCHER_WINDOW games doesn't catch
today (he may still DH or play another position he plays). That caps any catcher at 70% of games, inside what 2026
catchers actually sustained (no main catcher above 75% of his team's games; 90th percentile 68%). Without it the
optimizer caught the best framer in 76% of games, more than any real workload.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache

from backend import config, db
from backend.engine import defense, roster, workload
from backend.engine.hitting import batter_split, season_line
from backend.engine.matchups import batting_side
from backend.engine.pitching import pitcher_split

SLOT_PA = {1: 4.63, 2: 4.53, 3: 4.42, 4: 4.32, 5: 4.22, 6: 4.11, 7: 3.99, 8: 3.87, 9: 3.75}   # 2026 league
POSITIONS = ["C", "SS", "CF", "2B", "3B", "RF", "LF", "1B", "DH"]
WOBA_SCALE = 1.20
PYTH = 0.287
HOME_LOGIT = 0.16
REST_MAX_COST = 0.0025       # rest a tired hitter only if it costs at most 0.25 win-probability points today
PLATOON_PRIOR_PA = 400       # fade version: a hitter's own platoon split is trusted halfway at this many PA
AVG_PA = sum(SLOT_PA.values()) / 9      # plate appearances per lineup spot, to put offense in runs per game
CATCHER_MAX_STARTS, CATCHER_WINDOW = 7, 10      # at most 7 of the team's last 10 games behind the plate
CAP_REPLACES_CATCHER_REST = True                 # with the cap on, catchers skip the 6-straight-starts rest flag

VERSION = "marcel"           # "marcel" (projection_search.py) or "fade" (the earlier value_model_search.py model)


def set_version(v: str) -> None:
    """Switch the hitter/starter projection (for before/after comparisons) and clear every cached value."""
    global VERSION
    VERSION = v
    for f in (params, hitter_value, platoon, starter_quality):
        f.cache_clear()


@lru_cache(maxsize=1)
def params() -> dict:
    p = json.loads((config.REPO_ROOT / "data" / "lineup_params.json").read_text(encoding="utf-8"))
    if VERSION == "marcel" and "projection" in p:
        pr = p["projection"]
        return {"version": "marcel", "hitter": pr["hitter"], "k_hitter": pr["k_hitter"], "w_hitter": pr["w2025_hitter"],
                "platoon": "own", "platoon_pa": pr["platoon_pa"], "w_platoon": pr["platoon_w2025"],
                "pitcher": pr["pitcher"], "k_pitcher": pr["k_pitcher"], "w_pitcher": pr["w2025_pitcher"],
                "calibration": pr["calibration_slope"]}
    return p["value_model"] | {"version": "fade", "calibration": p.get("season_value_slope", 1.0)}


# Raw counts (wOBA numerator, xwOBA numerator, PA) for the Marcel pool: 2026 before the date, and 2025.
def _bat_counts(pid: int, d: str, hand: str | None) -> tuple[tuple, tuple]:
    cond, args = ("batter_id = ? AND p_throws = ?", [pid, hand]) if hand else ("batter_id = ?", [pid])
    q = "SELECT COALESCE(SUM(woba_num), 0) n, COALESCE(SUM(xwoba_num), 0) x, COALESCE(SUM(woba_den), 0) w FROM "
    a = db.one(q + f"statcast_batter_game WHERE {cond} AND game_date < ?", *args, d)
    b = db.one(q + f"statcast_batter_season WHERE season = 2025 AND {cond}", *args)
    return (a["n"], a["x"], a["w"]), (b["n"], b["x"], b["w"])


def _pit_counts(pid: int, d: str) -> tuple[tuple, tuple]:
    q = "SELECT COALESCE(SUM(woba_num), 0) n, COALESCE(SUM(xwoba_num), 0) x, COALESCE(SUM(woba_den), 0) w FROM "
    a = db.one(q + "statcast_pitcher_game WHERE pitcher_id = ? AND game_date < ?", pid, d)
    b = db.one(q + "statcast_pitcher_season WHERE season = 2025 AND pitcher_id = ?", pid)
    return (a["n"], a["x"], a["w"]), (b["n"], b["x"], b["w"])


def _pool(cur: tuple, prior: tuple, w25: float) -> tuple[float, float, float]:
    return tuple(c + w25 * p for c, p in zip(cur, prior))


def _rate(pool: tuple, metric: str) -> float | None:
    """wOBA, xwOBA (put on the wOBA scale) or their average from pooled counts; None with no plate appearances."""
    lg = league()
    if pool[2] <= 0:
        return None
    w, x = pool[0] / pool[2], pool[1] / pool[2] - lg["xwoba"] + lg["woba"]
    return {"woba": w, "xwoba": x, "blend": (w + x) / 2}[metric]


def _marcel(cur: tuple, prior: tuple, w25: float, k: float, metric: str) -> float:
    pool = _pool(cur, prior, w25)
    r, lg = _rate(pool, metric), league()["woba"]
    return lg if r is None else (r * pool[2] + lg * k) / (pool[2] + k)


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
    if p["version"] == "marcel":
        return _marcel(*_bat_counts(pid, d, None), p["w_hitter"], p["k_hitter"], p["hitter"])
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
    p = params()
    if p["platoon"] != "own":
        return lg_adj
    if p["version"] == "marcel":
        split = _pool(*_bat_counts(pid, d, throws), p["w_platoon"])
        overall = _pool(*_bat_counts(pid, d, None), p["w_platoon"])
        s, o = _rate(split, "woba"), _rate(overall, "woba")
        if s is None or o is None:
            return lg_adj
        return ((s - o) * split[2] + lg_adj * p["platoon_pa"]) / (split[2] + p["platoon_pa"])
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
    if p["version"] == "marcel":
        return _marcel(*_pit_counts(pid, d), p["w_pitcher"], p["k_pitcher"], p["pitcher"])
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


def _assign(values: dict[int, dict[str, float]], elig: dict[int, set[str]]) -> tuple[float, dict[str, int]] | None:
    """Best total value filling each position once (exact search over positions, memoized on who is used).
    values[player][position] = runs per game he is worth there (offense + defense at that position)."""
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
                if v + values[pid][order[i]] > top[0]:
                    top = (v + values[pid][order[i]], ((order[i], pid),) + rest)
        return top

    total, picks = best(0, frozenset())
    return None if total == -math.inf else (total, dict(picks))


def _order(d: str, sp_id: int, nine: dict[str, int]) -> list[tuple[int, int, str]]:
    """Best hitters bat most: sort by runs per PA, top of the order first."""
    ranked = sorted(nine.items(), key=lambda kv: -pa_runs(kv[1], d, sp_id))
    return [(slot, pid, pos) for slot, (pos, pid) in enumerate(ranked, start=1)]


def recent_catcher_starts(team_id: int, d: str) -> dict[int, int]:
    """Games each player started at catcher among the team's last CATCHER_WINDOW games before d."""
    pks = [r["game_pk"] for r in db.rows(
        "SELECT DISTINCT game_pk, game_date FROM batting_lines WHERE team_id = ? AND game_date < ? "
        "ORDER BY game_date DESC, game_pk DESC LIMIT ?", team_id, d, CATCHER_WINDOW)]
    if not pks:
        return {}
    marks = ",".join("?" * len(pks))
    return {r["player_id"]: r["n"] for r in db.rows(
        f"SELECT player_id, COUNT(*) n FROM batting_lines WHERE team_id = ? AND is_starter = 1 AND start_position = 'C' "
        f"AND game_pk IN ({marks}) GROUP BY 1", team_id, *pks)}


def best_lineup(team_id: int, d: str, sp_id: int, unavailable: set[int] = frozenset(), home: bool | None = None,
                catcher_recent: dict[int, int] | None = None, catcher_cap: bool = True) -> dict:
    """The lineup the win model rates best against starter sp_id, with every number behind it.
    catcher_recent overrides the catcher history read from the database (a season replay passes its own choices)."""
    hitters = [r for r in roster.active_roster(team_id, d) if not roster.is_pitcher(r) and r["player_id"] not in unavailable]
    values = {r["player_id"]: pa_runs(r["player_id"], d, sp_id) for r in hitters}
    elig = {r["player_id"]: eligible_positions(r["player_id"], d) for r in hitters}
    capped_notes = []
    if catcher_cap:
        recent = recent_catcher_starts(team_id, d) if catcher_recent is None else catcher_recent
        capped = {p for p in elig if "C" in elig[p] and recent.get(p, 0) >= CATCHER_MAX_STARTS}
        if capped and any("C" in elig[p] for p in elig if p not in capped):      # never leave nobody to catch
            for p in capped:
                elig[p] = elig[p] - {"C"}
                capped_notes.append(f"{roster.player_name(p)}: caught {recent[p]} of the team's last {CATCHER_WINDOW} "
                                    f"games, so he doesn't catch today (catchers are capped at {CATCHER_MAX_STARTS} of "
                                    f"{CATCHER_WINDOW}, about the most any 2026 catcher sustained); he can still DH")
    glove = {p: {pos: defense.runs_saved(p, pos, d, priced=True) for pos in elig[p]} for p in values}
    tired = {r["player_id"]: workload.rest_check(team_id, r["player_id"], d, r["position"]) for r in hitters}
    if catcher_cap and CAP_REPLACES_CATCHER_REST:
        # The cap is the catchers' workload rule (it already allows at most 7 straight); the 6-straight rest flag
        # would rest them a second time.
        for r in hitters:
            if r["position"] == "C":
                tired[r["player_id"]] = dict(tired[r["player_id"]], rest_suggested=False)

    def build(excluded: set[int]) -> tuple[float, list[tuple[int, int, str]]] | None:
        """(runs scored + runs saved on defense, lineup) for the best legal nine without the excluded players."""
        v = {p: {pos: AVG_PA * values[p] + glove[p][pos] for pos in elig[p]} for p in values if p not in excluded}
        got = _assign(v, {p: elig[p] for p in v})
        if not got:
            return None
        order = _order(d, sp_id, got[1])
        saved = sum(glove[p][pos] for _, p, pos in order)
        return expected_runs([(s, p) for s, p, _ in order], d, sp_id) + saved, order

    full = build(set())
    if full is None:
        raise ValueError("No legal lineup: not enough available hitters to cover every position.")
    net, order = full
    rested, rest_notes = set(), list(capped_notes)
    lg_runs = league()["rpg"]
    for pid in [p for _, p, _ in order if tired[p]["rest_suggested"]]:
        alt = build(rested | {pid})
        cost = (win_prob(net, lg_runs, home) - win_prob(alt[0], lg_runs, home)) if alt else 1.0
        name = roster.player_name(pid)
        if alt and cost <= REST_MAX_COST:
            rested.add(pid)
            net, order = alt
            rest_notes.append(f"{name}: resting him today costs {100 * cost:.2f} win-probability points, at most "
                              f"{100 * REST_MAX_COST:.2f}, so today is a good rest day ({tired[pid]['rest_note']})")
        elif not alt:
            rest_notes.append(f"{name}: plays; nobody else available can fill his position today. {tired[pid]['rest_note']}")
        else:
            rest_notes.append(f"{name}: plays; resting him today would cost {100 * cost:.2f} win-probability points "
                              f"(rest only on days costing {100 * REST_MAX_COST:.2f} or less). {tired[pid]['rest_note']}")
    names = {r["player_id"]: r["full_name"] for r in hitters}
    bats = {r["player_id"]: r["bat_side"] for r in hitters}
    in_lineup = {p for _, p, _ in order}
    saved = sum(glove[p][pos] for _, p, pos in order)
    return {
        "opposing_starter_id": sp_id,
        "lineup": [{"slot": s, "player_id": p, "name": names[p], "position": pos, "bats": bats[p],
                    "runs_per_pa_vs_avg": round(values[p], 4), "defense_runs_per_game": round(glove[p][pos], 3)}
                   for s, p, pos in order],
        "expected_runs": round(net - saved, 2),
        "defense_runs_saved_per_game": round(saved, 2),
        "rest_decisions": rest_notes,
        "bench_ranked": [{"player_id": p, "name": names[p], "runs_per_pa_vs_avg": round(values[p], 4),
                          "positions": sorted(elig[p] - {"DH"}),
                          "best_defense_runs_per_game": round(max([glove[p][x] for x in elig[p] - {"DH"}] or [0.0]), 3)}
                         for p in sorted(values, key=lambda p: -values[p]) if p not in in_lineup],
        "how": ("Win model: hitter xwOBA (2026 to date pooled with 2025, regressed toward league), his own platoon "
                "split vs this starter's hand, the starter's quality (same pooling) and usual depth, PA by batting-order "
                "slot, plus each fielder's runs saved at his position (multi-year Outs Above Average there; catcher "
                "framing). Maximized over legal positions; no catcher catches more than 7 of 10 games."),
    }
