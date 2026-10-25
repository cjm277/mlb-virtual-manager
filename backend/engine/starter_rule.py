"""Which of our starters should pitch today? A season-aware rotation rule (no LLM).

A five-man rotation gives every starter the same share of starts, so off-days are spent resting the best starters
an extra day while the fifth starter keeps his turn. The rule spends them on the best starters instead:

  1. Rotation: our pitchers who made a real start (12+ batters faced) for the team in the last 15 days and are on
     the active roster today.
  2. Rested: on 4+ days of rest (pitched day X, can start day X+5). 2026 data shows no measurable penalty for
     starting on 4 days of rest vs 5+ (value_verification.md, Check 3).
  3. Cap: no starter takes more than EXTRA_STARTS starts beyond his fair share (one turn in `cycle` team games
     since he joined the rotation), so the best starters gain about two starts a season, not a dozen. Innings limits
     and injury risk can't be priced from this data, so the cap keeps the workload close to normal.
  4. Pick the rested, under-cap starter who costs the fewest runs: his wOBA allowed (Marcel projection, as in the
     lineup model) over the share of the game he usually pitches. If nobody qualifies, the man on turn (longest
     rested) starts.

The same function drives the app's model_starter tool and the full-season replay that values it
(scripts/starter_rule_replay.py), so the replay scores exactly what the app recommends.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from backend import db
from backend.engine import roster

EXTRA_STARTS = 2        # at most this many starts beyond a fair rotation share
MIN_DAYS_BETWEEN = 5    # 4 days of rest
ROTATION_WINDOW = 15    # days back that define the rotation
REAL_START_BF = 12


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def choose(members: list[int], last_start: dict[int, str | None], starts: dict[int, int], fair: dict[int, float],
           cost: dict[int, float], d: str) -> dict:
    """The rule itself. members: rotation pitchers; last_start: date of each one's last start (None = rested);
    starts: starts each has made since joining; fair: his fair share counting today (team games since joining, today
    included, / cycle); cost: runs he costs vs a league-average starter today (lower is better)."""
    rested = [p for p in members if last_start.get(p) is None or _days(last_start[p], d) >= MIN_DAYS_BETWEEN]
    on_turn = min(members, key=lambda p: (last_start.get(p) or "0000", cost[p])) if members else None
    allowed = [p for p in rested if starts.get(p, 0) + 1 <= fair.get(p, 0.0) + EXTRA_STARTS + 1e-9]
    if allowed:
        pick = min(allowed, key=lambda p: cost[p])
        why = "best rested starter under his extra-start cap"
    else:
        pick, why = on_turn, "nobody rested and under the cap: the man on turn"
    return {"pick": pick, "on_turn": on_turn, "why": why, "rested": rested, "allowed": allowed}


# ---------------------------------------------------------------------------
# The app: today's recommendation from the team's real history
# ---------------------------------------------------------------------------

def _team_starts_before(team_id: int, d: str) -> list[dict]:
    return db.rows("""SELECT p.game_pk, p.game_date, p.player_id, p.bf FROM pitching_lines p
                      WHERE p.team_id = ? AND p.is_starter = 1 AND p.game_date < ? AND p.game_date >= ?
                      ORDER BY p.game_date, p.game_pk""", team_id, d, f"{d[:4]}-01-01")


def team_games_before(team_id: int, d: str) -> list[str]:
    return [r["game_date"] for r in db.rows(
        "SELECT game_date FROM games WHERE (home_team_id = ? OR away_team_id = ?) AND game_date < ? AND game_date >= ? "
        "ORDER BY game_date, game_number", team_id, team_id, d, f"{d[:4]}-01-01")]


@lru_cache(maxsize=None)
def _stints(team_id: int, pid: int) -> tuple[tuple[str, str], ...]:
    return tuple((r["start_date"], r["end_date"]) for r in db.rows(
        "SELECT start_date, end_date FROM roster_stints WHERE team_id = ? AND player_id = ?", team_id, pid))


def _active(team_id: int, pid: int, d: str) -> bool:
    """On the team's active roster that day (an injured-list stint doesn't count toward his fair share)."""
    return any(a <= d <= b for a, b in _stints(team_id, pid))


def rotation_state(team_id: int, d: str, history: list[dict] | None = None, cycle: int = 5) -> dict:
    """Members, last starts, starts and fair shares from a list of the team's starts before d
    (default: what really happened)."""
    hist = [dict(r) for r in (_team_starts_before(team_id, d) if history is None else history)]
    lo = (date.fromisoformat(d) - timedelta(days=ROTATION_WINDOW)).isoformat()
    active = {r["player_id"] for r in roster.active_roster(team_id, d) if roster.is_pitcher(r)}
    members = sorted({r["player_id"] for r in hist if r["game_date"] >= lo and (r.get("bf") or 99) >= REAL_START_BF}
                     & active)
    games = team_games_before(team_id, d)
    last, starts, first = {}, {}, {}
    for r in hist:
        p = r["player_id"]
        last[p] = r["game_date"]
        starts[p] = starts.get(p, 0) + 1
        first.setdefault(p, r["game_date"])
    fair = {p: (sum(1 for g in games if g >= first[p] and _active(team_id, p, g)) + 1) / cycle if p in first else 0.0
            for p in members}
    return {"members": members, "last_start": {p: last.get(p) for p in members},
            "starts": {p: starts.get(p, 0) for p in members}, "fair": fair}


def team_cycle(team_id: int, d: str, game_number: int = 1) -> int:
    """The team's rotation length (5 or 6), learned from its recent turns as in the rotation predictor."""
    from backend.engine import rotation
    return rotation._cycle_length(rotation._turns_before(team_id, d, game_number, limit=30))


def starter_cost(pid: int, d: str) -> float:
    """Runs this starter costs (positive) or saves vs a league-average starter, as in the win model."""
    from backend.engine import winmodel
    lg = winmodel.league()
    share = min(winmodel.starter_depth(pid, d) / lg["team_pa"], 0.9)
    return share * sum(winmodel.SLOT_PA.values()) * (winmodel.starter_quality(pid, d) - lg["woba"]) / winmodel.WOBA_SCALE


def recommend(team_id: int, d: str, unavailable: set[int] = frozenset()) -> dict:
    from backend.engine.common import is_future
    if is_future(d):
        return {"recommended": None, "note": "2027 games: no rotation has been used yet, so there is no rest or "
                "workload to manage. Pick from starter_options as usual."}
    s = rotation_state(team_id, d, cycle=team_cycle(team_id, d))
    members = [p for p in s["members"] if p not in unavailable]
    if not members:
        return {"recommended": None, "note": "No rotation starter found in the last 15 days; pick from starter_options."}
    cost = {p: starter_cost(p, d) for p in members}
    c = choose(members, s["last_start"], s["starts"], s["fair"], cost, d)
    rows = [{"player_id": p, "name": roster.player_name(p),
             "days_rest": (_days(s["last_start"][p], d) - 1) if s["last_start"][p] else None,
             "starts": s["starts"][p], "fair_share_so_far": round(s["fair"][p], 1),
             "runs_vs_average_starter": round(cost[p], 2), "rested": p in c["rested"], "under_cap": p in c["allowed"]}
            for p in sorted(members, key=lambda p: cost[p])]
    return {"recommended": {"player_id": c["pick"], "name": roster.player_name(c["pick"])},
            "on_turn": {"player_id": c["on_turn"], "name": roster.player_name(c["on_turn"])},
            "why": c["why"], "rotation": rows,
            "rule": (f"Start the best rested starter (4+ days of rest) who has made no more than {EXTRA_STARTS} starts "
                     "beyond his fair rotation share; off-days go to the best starters, not the fifth starter.")}
