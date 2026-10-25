"""Defensive value per game: fielders' range (Outs Above Average at that position) and catchers' framing.

Savant publishes these for full seasons only, so a game uses only COMPLETED seasons before it (2023-2025 for a
2026 game, 2024-2026 for a 2027 game). That keeps the backtest free of look-ahead.

- Fielders: fielding runs prevented AT THAT POSITION over the last three seasons, weighted toward the most
  recent, per 9 innings he played there, regressed toward average. A player with no history at that position
  gets what such players actually did (measured): worse if he has played elsewhere (out of position), slightly
  worse if he has no MLB fielding history at all.
- Catchers: framing runs per pitch received over the last three seasons, times the pitches in a typical game,
  regressed the same way.
- DH: no defense.
The season weights and how hard to regress were chosen by how well they predicted the next season
(scripts/defense_rating_search.py). How much a rated run actually moves runs allowed was measured on 2026 games
(scripts/defense_params.py). Both are stored in data/lineup_params.json.
"""

from __future__ import annotations

import json
from functools import lru_cache

from backend import config, db

PITCHES_PER_GAME = 147          # pitches a team's catchers receive per game (2026)
DEFAULT_RATING = {"season_weights": [1.0, 0.8, 0.6], "k_innings": 600, "k_pitches": 3000,
                  "new_position_per_game": 0.0, "no_history_per_game": 0.0}


@lru_cache(maxsize=1)
def _params() -> dict:
    f = config.REPO_ROOT / "data" / "lineup_params.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def rating_settings() -> dict:
    return _params().get("defense_rating", DEFAULT_RATING)


def weights() -> dict:
    return _params().get("defense", {"fielding": 0.0, "framing": 0.0})


def rating_season(game_date: str) -> int:
    return int(game_date[:4]) - 1


@lru_cache(maxsize=None)
def _history(pid: int, pos: str) -> dict[int, tuple[float, float]]:
    return {r["season"]: (r["fielding_runs_prevented"] or 0.0, r["innings"] or 0.0) for r in db.rows(
        "SELECT season, fielding_runs_prevented, innings FROM fielding_by_position WHERE player_id = ? AND position = ?",
        pid, pos)}


@lru_cache(maxsize=None)
def _framing(pid: int) -> dict[int, tuple[float, float]]:
    return {r["season"]: (r["framing_runs"] or 0.0, r["pitches"] or 0.0) for r in db.rows(
        "SELECT season, framing_runs, pitches FROM framing_history WHERE player_id = ? ", pid)}


@lru_cache(maxsize=None)
def _played_anywhere(pid: int, first: int, last: int) -> bool:
    return db.one("SELECT 1 x FROM fielding_by_position WHERE player_id = ? AND season BETWEEN ? AND ? AND innings > 0",
                  pid, first, last) is not None


def fielding_per_game(pid: int, pos: str, last_season: int, settings: dict | None = None) -> float:
    s = {**DEFAULT_RATING, **(settings or rating_settings())}
    hist = _history(pid, pos)
    runs = inn = 0.0
    for i, w in enumerate(s["season_weights"]):
        frp, ip = hist.get(last_season - i, (0.0, 0.0))
        runs += w * frp
        inn += w * ip
    if inn:
        return 9 * runs / (inn + s["k_innings"])
    first = last_season - len(s["season_weights"]) + 1
    return s["new_position_per_game"] if _played_anywhere(pid, first, last_season) else s["no_history_per_game"]


def framing_per_game(pid: int, last_season: int, settings: dict | None = None) -> float:
    s = settings or rating_settings()
    hist = _framing(pid)
    runs = pitches = 0.0
    for i, w in enumerate(s["season_weights"]):
        fr, n = hist.get(last_season - i, (0.0, 0.0))
        runs += w * fr
        pitches += w * n
    return PITCHES_PER_GAME * runs / (pitches + s["k_pitches"]) if pitches else 0.0


def runs_saved(pid: int, pos: str, game_date: str, w: dict | None = None) -> float:
    """Runs this player saves per game at this position (positive = better than average), as measured."""
    w = weights() if w is None else w
    season = rating_season(game_date)
    if pos == "DH":
        return 0.0
    if pos == "C":
        return w["framing"] * framing_per_game(pid, season)
    return w["fielding"] * fielding_per_game(pid, pos, season)


def team_runs_saved(fielders: list[tuple[int, str]], game_date: str, w: dict | None = None) -> float:
    return sum(runs_saved(pid, pos, game_date, w) for pid, pos in fielders)
