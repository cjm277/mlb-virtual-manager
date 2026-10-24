"""Teams, the games two teams played, and the context of one game."""

from __future__ import annotations

from backend import db
from backend.engine.common import prior_weight


def teams() -> list[dict]:
    return [dict(r) for r in db.rows("SELECT team_id, name, abbrev, team_name, league, division FROM teams ORDER BY name")]


def team(team_id: int) -> dict:
    r = db.one("SELECT team_id, name, abbrev, team_name, league, division, venue FROM teams WHERE team_id = ?", team_id)
    if not r:
        raise ValueError(f"Unknown team_id {team_id}")
    return dict(r)


def games_between(team_id: int, opponent_id: int) -> list[dict]:
    """Every 2026 regular-season game between two teams (for the date picker)."""
    return [{
        "game_pk": r["game_pk"], "game_date": r["game_date"], "game_number": r["game_number"],
        "home_away": "home" if r["home_team_id"] == team_id else "away", "venue": r["venue"],
    } for r in db.rows("""
        SELECT game_pk, game_date, game_number, home_team_id, venue FROM games
        WHERE (home_team_id = ? AND away_team_id = ?) OR (home_team_id = ? AND away_team_id = ?)
        ORDER BY game_date, game_number""", team_id, opponent_id, opponent_id, team_id)]


def game(game_pk: int) -> dict:
    r = db.one("SELECT * FROM games WHERE game_pk = ?", game_pk)
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
    w = prior_weight(g["game_date"])
    return {
        "game_pk": game_pk, "game_date": g["game_date"], "game_number": g["game_number"],
        "day_night": g["day_night"], "venue": g["venue"],
        "team": team(team_id)["name"], "team_id": team_id, "team_record": record_before(team_id, g["game_date"]),
        "opponent": team(opp_id)["name"], "opponent_id": opp_id, "opponent_record": record_before(opp_id, g["game_date"]),
        "home_away": "home" if home else "away",
        "bats_last": home,
        "stats_through": "the day before the game",
        "weight_on_2025_stats": f"{round(w * 100)}%",
    }
