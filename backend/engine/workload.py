"""Position-player workload: how many games in a row a hitter has started, and when a rest day is suggested.

The thresholds come from 2026 data (scripts/rest_thresholds.py): among regulars (100+ starts), a run of
straight starts longer than three out of four real runs is unusual. That is 6 for catchers and 10 for
everyone else. Past that point a rest day is suggested, not forced: the Bench Coach decides whether today is
the day, ideally a day when the player's matchup is weak, so the rest costs the least.
"""

from __future__ import annotations

from backend import db
from backend.engine.common import is_future

REST_AFTER = {"C": 6, "other": 10}   # 75th percentile of real 2026 runs of straight starts (see docstring)


def consecutive_starts(team_id: int, player_id: int, game_date: str) -> int:
    """Team games in a row he started, counting back from the team's last game before game_date."""
    team_games = [r["game_pk"] for r in db.rows(
        """SELECT DISTINCT b.game_pk, b.game_date FROM batting_lines b WHERE b.team_id = ? AND b.game_date < ?
           ORDER BY b.game_date DESC, b.game_pk DESC LIMIT 40""", team_id, game_date)]
    started = {r["game_pk"] for r in db.rows(
        "SELECT game_pk FROM batting_lines WHERE player_id = ? AND team_id = ? AND is_starter = 1 AND game_date < ?",
        player_id, team_id, game_date)}
    run = 0
    for pk in team_games:
        if pk not in started:
            break
        run += 1
    return run


def rest_check(team_id: int, player_id: int, game_date: str, position: str | None) -> dict:
    if is_future(game_date):
        return {"consecutive_starts": None, "rest_suggested": False,
                "rest_note": "No 2027 games played yet, so there is no workload to manage."}
    run = consecutive_starts(team_id, player_id, game_date)
    limit = REST_AFTER["C" if position == "C" else "other"]
    out = {"consecutive_starts": run, "rest_suggested": run >= limit}
    if out["rest_suggested"]:
        out["rest_note"] = (f"{run} straight starts; a rest day is suggested after {limit} for "
                            f"{'catchers' if position == 'C' else 'position players'} (2026 data).")
    return out
