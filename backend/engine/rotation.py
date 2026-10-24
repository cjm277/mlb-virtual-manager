"""Predict a team's starting pitcher for a game from its rotation order and rest.

The rule a manager would use:
  1. Rotation turns: for each recent team game, the pitcher who took the turn is the starter if he went
     3+ innings or threw 50+ pitches. If an opener started, the "bulk" pitcher who followed takes the turn.
  2. Learn the team's cycle length: the usual number of turns between one pitcher's starts
     (5 for a five-man rotation, 6 for a six-man rotation or one with a regular bullpen day).
  3. Candidates = the pitchers who took the last (cycle + 2) turns. Drop anyone not on the active
     roster that day (injured, optioned) or on fewer than 4 days of rest.
  4. A starting pitcher added to the active roster that very day (called up or back from the injured list)
     is almost always joining to start, so he goes first.
  5. Otherwise the pitcher whose last turn was closest to one full cycle ago is "on turn"
     (if two are equally close, the one more overdue).
Early in the season (fewer than 5 turns taken), the rotation is filled out with the active pitchers who
started the most games in 2025. MLB's listed probable starter is never used here; it is only used
afterwards to measure accuracy.

2027 games (not yet played) are a projection instead: the team's established starters on its 2027 roster
(most 2026 starts first, the workhorse on Opening Day), cycled through the team's 2027 schedule in order.
"""

from __future__ import annotations

from datetime import timedelta

from backend import db
from backend.engine.common import is_future, last_played_day, to_date
from backend.engine.roster import active_roster, is_pitcher, player_info

ROTATION_SIZE = 5
MIN_REST = 4      # days of rest between starts (pitched day X, next start X+5)
REAL_START_OUTS = 9
REAL_START_PITCHES = 50


def _turns_before(team_id: int, game_date: str, game_number: int, limit: int = 20) -> list[tuple[int, str]]:
    """(pitcher, date) of the pitcher who took each recent rotation turn, most recent first."""
    lines = db.rows("""
        SELECT pl.game_pk, pl.game_date, g.game_number, pl.player_id, pl.is_starter, pl.outs, pl.pitches
        FROM pitching_lines pl JOIN games g USING(game_pk)
        WHERE pl.team_id = ?1 AND pl.game_pk IN (
            SELECT g2.game_pk FROM games g2
            WHERE (g2.home_team_id = ?1 OR g2.away_team_id = ?1)
              AND (g2.game_date < ?2 OR (g2.game_date = ?2 AND g2.game_number < ?3))
            ORDER BY g2.game_date DESC, g2.game_number DESC LIMIT ?4)
        ORDER BY pl.game_date DESC, g.game_number DESC, pl.appearance_order""",
        team_id, game_date, game_number, limit)
    turns, by_game = [], {}
    for r in lines:
        by_game.setdefault(r["game_pk"], []).append(r)
    for pk, pitchers in sorted(by_game.items(), key=lambda kv: (kv[1][0]["game_date"], kv[1][0]["game_number"]),
                               reverse=True):
        starter = next((p for p in pitchers if p["is_starter"]), None)
        real = lambda p: p["outs"] >= REAL_START_OUTS or p["pitches"] >= REAL_START_PITCHES  # noqa: E731
        if starter and real(starter):
            turns.append((starter["player_id"], starter["game_date"]))
        else:
            bulk = max(pitchers, key=lambda p: p["pitches"])
            if real(bulk):
                turns.append((bulk["player_id"], bulk["game_date"]))
    return turns


def _last_appearance(player_id: int, game_date: str) -> str | None:
    r = db.one("SELECT MAX(game_date) d FROM pitching_lines WHERE player_id = ? AND game_date < ?", player_id, game_date)
    return r["d"] if r else None


def _starter_history(player_id: int, game_date: str) -> int:
    """2026 starts before the game plus 2025 starts."""
    r = db.one("SELECT COUNT(*) n FROM pitching_lines WHERE player_id = ? AND is_starter = 1 AND game_date < ?",
               player_id, game_date)
    p = db.one("SELECT MAX(gs) gs FROM season_pitching WHERE season = 2025 AND player_id = ?", player_id)
    return (r["n"] or 0) + ((p["gs"] or 0) if p else 0)


def _candidate(pid: int, last_turn: str | None, game_date: str, active: set[int], note: str = "") -> dict:
    last_app = _last_appearance(pid, game_date)
    rest = (to_date(game_date) - to_date(last_app)).days - 1 if last_app else None
    info = player_info(pid) or {}
    return {"player_id": pid, "name": info.get("full_name"), "throws": info.get("pitch_hand"),
            "last_turn": last_turn, "days_rest": rest, "active": pid in active,
            "eligible": pid in active and (rest is None or rest >= MIN_REST), "note": note}


def _cycle_length(turns: list[tuple[int, str]]) -> int:
    """Median number of turns between a pitcher's consecutive turns (5 if unclear)."""
    seen: dict[int, int] = {}
    gaps = []
    for k, (pid, _) in enumerate(turns):
        if pid in seen:
            gaps.append(k - seen[pid])
        seen[pid] = k
    gaps = sorted(g for g in gaps if 3 <= g <= 8)
    return gaps[len(gaps) // 2] if gaps else ROTATION_SIZE


def _starts_2026(player_id: int) -> tuple[int, int]:
    r = db.one("SELECT SUM(is_starter) gs, SUM(outs) outs FROM pitching_lines WHERE player_id = ?", player_id)
    return (r["gs"] or 0, r["outs"] or 0)


def _starter_weight(player_id: int) -> float:
    """2026 starts plus half credit for 2025 starts (so a starter hurt all of 2026 still counts)."""
    p = db.one("SELECT MAX(gs) gs FROM season_pitching WHERE season = 2025 AND player_id = ?", player_id)
    return _starts_2026(player_id)[0] + 0.5 * ((p["gs"] or 0) if p else 0)


def projected_rotation(team_id: int) -> list[int]:
    """Projected 2027 rotation: the team's established starters on its 2027 roster, workhorse first.

    The 2027 roster is the end-of-2026 roster plus players who ended 2026 injured (assumed healthy), so the
    rotation is built from everyone's starting record rather than the injury-depleted September rotation.
    The number of starters (5 or 6) is the team's 2026 cycle length.
    """
    after_season = (to_date(last_played_day()) + timedelta(days=1)).isoformat()
    cycle = min(max(_cycle_length(_turns_before(team_id, after_season, 1, limit=30)), 5), 6)
    pool = {r["player_id"] for r in active_roster(team_id, after_season) if is_pitcher(r)}
    weights = {pid: _starter_weight(pid) for pid in pool}
    starters = sorted((pid for pid, w in weights.items() if w >= 5), key=lambda pid: -weights[pid])
    return starters[:cycle]


def _project_2027(team_id: int, game_date: str, game_number: int) -> dict:
    rot = projected_rotation(team_id)
    n = db.one("""SELECT COUNT(*) n FROM future_games WHERE (home_team_id = ?1 OR away_team_id = ?1)
                  AND (game_date < ?2 OR (game_date = ?2 AND game_number < ?3))""", team_id, game_date, game_number)["n"]
    if not rot:
        return {"predicted": None, "confidence": "low", "method": "no 2026 starters on the end-of-season roster",
                "cycle_length": 0, "next_most_likely": [], "rotation_considered": []}
    candidates = []
    for i, pid in enumerate(rot):
        info = player_info(pid) or {}
        gs, outs = _starts_2026(pid)
        candidates.append({"player_id": pid, "name": info.get("full_name"), "throws": info.get("pitch_hand"),
                           "rotation_spot": i + 1, "starts_2026": gs, "ip_2026": f"{outs // 3}.{outs % 3}"})
    pick = candidates[n % len(rot)]
    neighbors = [candidates[(n - 1) % len(rot)]["name"], candidates[(n + 1) % len(rot)]["name"]]
    return {
        "predicted": pick, "confidence": "projection",
        "method": (f"2027 projection: the team's established starters ({len(rot)}, most 2026 starts first) cycled through "
                   f"the 2027 schedule; this is the team's game {n + 1} of 2027. Off days, injuries and offseason "
                   "moves can change the real order."),
        "cycle_length": len(rot), "next_most_likely": list(dict.fromkeys(neighbors)),
        "rotation_considered": candidates,
    }


def predict_starter(team_id: int, game_date: str, game_number: int = 1) -> dict:
    if is_future(game_date):
        return _project_2027(team_id, game_date, game_number)
    turns = _turns_before(team_id, game_date, game_number, limit=30)
    cycle = _cycle_length(turns)
    rotation: list[tuple[int, str | None]] = []
    turns_ago: dict[int, int] = {}
    for k, (pid, d) in enumerate(turns[: cycle + 2]):
        if pid not in turns_ago:
            turns_ago[pid] = k
            rotation.append((pid, d))

    roster = active_roster(team_id, game_date)
    active = {r["player_id"] for r in roster if is_pitcher(r)}
    method = "rotation order"
    if len(turns) < ROTATION_SIZE:
        method = "rotation order, filled with 2025 starters (early season)"
        for f in db.rows("""SELECT player_id, MAX(gs) gs FROM season_pitching WHERE season = 2025 AND gs > 0
                            GROUP BY player_id ORDER BY gs DESC"""):
            if f["player_id"] in active and f["player_id"] not in {p for p, _ in rotation}:
                rotation.append((f["player_id"], None))
            if len(rotation) == ROTATION_SIZE:
                break
    candidates = [_candidate(pid, d, game_date, active) for pid, d in rotation]
    for c in candidates:
        c["turns_ago"] = turns_ago.get(c["player_id"])

    # Starters joining the active roster today (call-up or back from the injured list).
    in_rotation = {c["player_id"] for c in candidates}
    joining = db.rows("""SELECT player_id FROM roster_stints WHERE team_id = ? AND start_date = ?
                         AND position IN ('P', 'TWP')""", team_id, game_date)
    arrivals = [_candidate(r["player_id"], None, game_date, active, "joined the active roster today")
                for r in joining if r["player_id"] not in in_rotation and _starter_history(r["player_id"], game_date) >= 3]
    arrivals = [a for a in arrivals if a["eligible"]]

    # On turn = last pitched closest to one full cycle ago; ties go to the more overdue pitcher.
    # (Early-season fill-ins with no turn yet count as fully due.)
    target = cycle - 1
    due = lambda c: (abs((c["turns_ago"] if c["turns_ago"] is not None else target) - target),  # noqa: E731
                     -(c["turns_ago"] if c["turns_ago"] is not None else target))
    eligible = sorted((c for c in candidates if c["eligible"]), key=due)
    if arrivals:
        pick, confidence = arrivals[0], "medium"
        method += "; a starter joined the roster today"
    elif eligible:
        pick = eligible[0]
        confidence = "high" if pick["turns_ago"] == target and 4 <= (pick["days_rest"] or 0) <= 6 else "medium"
    else:
        # Nobody in the rotation is rested: look for a rested spot starter on the active roster.
        spot = [_candidate(pid, None, game_date, active, "spot starter: rested, has started games before")
                for pid in active - in_rotation]
        spot = sorted((c for c in spot if c["eligible"] and _starter_history(c["player_id"], game_date) >= 3),
                      key=lambda c: -_starter_history(c["player_id"], game_date))
        pick, confidence = (spot[0] if spot else None), "low"
        arrivals = spot[:2]
        method += "; no rotation starter fully rested, so a spot starter or bullpen game is likely"
    return {"predicted": pick, "confidence": confidence, "method": method, "cycle_length": cycle,
            "next_most_likely": [c["name"] for c in (arrivals + eligible) if c is not pick][:2],
            "rotation_considered": candidates + arrivals}
