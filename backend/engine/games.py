"""Teams, the games two teams played, and the context of one game."""

from __future__ import annotations

from backend import db
from backend.engine.common import is_future, prior_weight, stats_basis


def teams() -> list[dict]:
    return [dict(r) for r in db.rows("SELECT team_id, name, abbrev, team_name, league, division FROM teams ORDER BY name")]


def team(team_id: int) -> dict:
    r = db.one("SELECT team_id, name, abbrev, team_name, league, division, venue FROM teams WHERE team_id = ?", team_id)
    if not r:
        raise ValueError(f"Unknown team_id {team_id}")
    return dict(r)


def games_between(team_id: int, opponent_id: int, season: int | None = None) -> list[dict]:
    """Every regular-season game between two teams: 2026 (played) and 2027 (scheduled), for the date picker."""
    out = []
    for table, yr in (("games", 2026), ("future_games", 2027)):
        if season and season != yr:
            continue
        out += [{
            "game_pk": r["game_pk"], "season": yr, "game_date": r["game_date"], "game_number": r["game_number"],
            "home_away": "home" if r["home_team_id"] == team_id else "away", "venue": r["venue"],
        } for r in db.rows(f"""
            SELECT game_pk, game_date, game_number, home_team_id, venue FROM {table}
            WHERE (home_team_id = ? AND away_team_id = ?) OR (home_team_id = ? AND away_team_id = ?)
            ORDER BY game_date, game_number""", team_id, opponent_id, opponent_id, team_id)]
    return out


def game(game_pk: int) -> dict:
    """A 2026 game (played) or a 2027 game (scheduled)."""
    r = db.one("SELECT *, 2026 AS season FROM games WHERE game_pk = ?", game_pk)
    if not r:
        r = db.one("SELECT * FROM future_games WHERE game_pk = ?", game_pk)
    if not r:
        raise ValueError(f"Unknown game_pk {game_pk}")
    return dict(r)


def record_before(team_id: int, game_date: str) -> str:
    r = db.one("""SELECT
        SUM(CASE WHEN (home_team_id = ?1 AND home_score > away_score) OR (away_team_id = ?1 AND away_score > home_score)
                 THEN 1 ELSE 0 END) AS w,
        SUM(CASE WHEN (home_team_id = ?1 AND home_score < away_score) OR (away_team_id = ?1 AND away_score < home_score)
                 THEN 1 ELSE 0 END) AS l
        FROM games WHERE (home_team_id = ?1 OR away_team_id = ?1) AND game_date < ?2""", team_id, game_date)
    return f"{r['w'] or 0}-{r['l'] or 0}"


def game_context(game_pk: int, team_id: int) -> dict:
    """Facts about the game from the managed team's side. The final score is deliberately left out."""
    g = game(game_pk)
    if team_id not in (g["home_team_id"], g["away_team_id"]):
        raise ValueError(f"Team {team_id} did not play in game {game_pk}")
    home = g["home_team_id"] == team_id
    opp_id = g["away_team_id"] if home else g["home_team_id"]
    d = g["game_date"]
    future = is_future(d)
    record = "2026 final record" if future else "record going in"
    ctx = {
        "game_pk": game_pk, "season": g["season"], "game_date": d, "game_number": g["game_number"],
        "day_night": g["day_night"], "venue": g["venue"],
        "team": team(team_id)["name"], "team_id": team_id, f"team_{record.replace(' ', '_')}": record_before(team_id, d),
        "opponent": team(opp_id)["name"], "opponent_id": opp_id,
        f"opponent_{record.replace(' ', '_')}": record_before(opp_id, d),
        "home_away": "home" if home else "away",
        "bats_last": home,
        "stats_basis": stats_basis(d),
    }
    if future:
        ctx["roster_basis"] = ("Each team's active roster at the end of the 2026 season. Offseason moves "
                               "(free agency, trades) are not known and are not modeled.")
    else:
        ctx["weight_on_2025_stats"] = f"{round(prior_weight(d) * 100)}%"
    return ctx
