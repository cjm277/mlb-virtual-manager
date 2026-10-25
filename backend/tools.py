"""The tools the agents call. Plain Python over the data snapshot; no LLM inside.

Design rules:
- Every tool takes the game (game_pk) and works out the date itself, so an agent can never ask for
  stats from after the game. All stats are through the day before the game.
- Outputs are compact JSON-ready dicts (fewer tokens per call).
- Bad inputs raise ValueError with a plain message, which the agent framework hands back to the
  model so it can correct itself.

Docstrings are written as tool descriptions: the agent reads them to decide what to call.
"""

from __future__ import annotations

from backend.engine import bullpen, games, hitting, lineup, matchups, pitching, rotation, roster, workload
from backend.engine.common import is_future


def _game(game_pk: int, team_id: int | None = None) -> dict:
    g = games.game(game_pk)
    if team_id is not None and team_id not in (g["home_team_id"], g["away_team_id"]):
        raise ValueError(f"Team {team_id} did not play in game {game_pk}. "
                         f"Teams in this game: {g['home_team_id']} and {g['away_team_id']}.")
    return g


def _on_roster(team_id: int, game_date: str, player_id: int) -> None:
    if player_id not in {r["player_id"] for r in roster.active_roster(team_id, game_date)}:
        raise ValueError(f"Player {player_id} is not on team {team_id}'s active roster for this game.")


# ---------------------------------------------------------------------------
# Game and availability (Manager, Team Doctor)
# ---------------------------------------------------------------------------

def get_game_context(game_pk: int, team_id: int) -> dict:
    """Facts about the game from our team's side: date, home/away, ballpark, both teams' records going in,
    and how much weight 2025 stats still carry this early in the season."""
    _game(game_pk, team_id)
    return games.game_context(game_pk, team_id)


def get_roster_and_injuries(game_pk: int, team_id: int) -> dict:
    """A team's available players for this game (hitters and pitchers, with position and handedness) and the
    players who are out: injured list (with the injury and since when) or other lists. Only available players
    can play. For a 2027 game the roster is the end-of-2026 roster, and players who ended 2026 injured are
    included with a health_note to confirm."""
    g = _game(game_pk, team_id)
    active = roster.active_roster(team_id, g["game_date"])

    def short(r: dict) -> dict:
        row = {"player_id": r["player_id"], "name": r["full_name"], "position": r["position"],
               "bats": r["bat_side"], "throws": r["pitch_hand"]}
        if r.get("health_note"):
            row["health_note"] = r["health_note"]
        return row

    def hitter(r: dict) -> dict:
        w = workload.rest_check(team_id, r["player_id"], g["game_date"], r["position"])
        row = short(r) | {"consecutive_starts": w["consecutive_starts"]}
        if w["rest_suggested"]:
            row |= {"rest_suggested": True, "rest_note": w["rest_note"]}
        return row

    future = is_future(g["game_date"])
    return {
        "team": games.team(team_id)["name"],
        "hitters": [hitter(r) for r in active if not roster.is_pitcher(r)],
        "pitchers": [short(r) for r in active if roster.is_pitcher(r)],
        "out": roster.unavailable_list(team_id, g["game_date"]),
        "note": ("2027 game: end-of-2026 roster; offseason moves are not modeled. Players with a health_note "
                 "ended 2026 injured and are assumed healthy." if future
                 else "Active roster as reported by MLB for the game date."),
    }


def get_bullpen_status(game_pk: int, team_id: int) -> dict:
    """Every active pitcher's recent workload going into this game. Relievers are marked available, limited,
    or unavailable by fixed rules (listed in the output); starters are listed with days of rest."""
    g = _game(game_pk, team_id)
    return bullpen.bullpen_status(team_id, g["game_date"])


# ---------------------------------------------------------------------------
# Players (Scouts, coaches)
# ---------------------------------------------------------------------------

def get_hitter_profile(game_pk: int, player_id: int) -> dict:
    """One hitter in depth: overall, vs left-handed and vs right-handed pitchers, vs fastballs / breaking balls /
    offspeed, season counting stats and where he has started in the field, last 14 days, sprint speed and
    defense. Every rate carries its sample size and a small/moderate/ok flag."""
    g = _game(game_pk)
    if not roster.player_info(player_id):
        raise ValueError(f"Unknown player_id {player_id}.")
    return hitting.hitter_profile(player_id, g["game_date"])


def get_pitcher_profile(game_pk: int, player_id: int) -> dict:
    """One pitcher in depth: season line, results allowed overall and vs left-/right-handed hitters, and his
    arsenal (each pitch's usage, velocity, spin, whiff %, xwOBA allowed, run value per 100 pitches), plus how
    his pitch mix changes against lefties vs righties."""
    g = _game(game_pk)
    if not roster.player_info(player_id):
        raise ValueError(f"Unknown player_id {player_id}.")
    return pitching.pitcher_profile(player_id, g["game_date"])


def get_hitters_overview(game_pk: int, team_id: int) -> list[dict]:
    """A one-row-per-hitter table for a team's active hitters: xwOBA overall and vs LHP/RHP, K %, BB %,
    positions started this season, sprint speed, games started in a row (rest_suggested past 6 for catchers,
    10 for others), and a sample flag. Use this before asking for single
    profiles; it is much cheaper."""
    g = _game(game_pk, team_id)
    d = g["game_date"]
    out = []
    for r in roster.active_roster(team_id, d):
        if roster.is_pitcher(r):
            continue
        pid = r["player_id"]
        overall = hitting.batter_split(pid, d)
        vs_l = hitting.batter_split(pid, d, "L", keys=["xwoba"])
        vs_r = hitting.batter_split(pid, d, "R", keys=["xwoba"])
        line = hitting.season_line(pid, d)
        sd = hitting.speed_and_defense(pid)
        w = workload.rest_check(team_id, pid, d, r["position"])
        out.append({
            "player_id": pid, "name": r["full_name"], "position": r["position"], "bats": r["bat_side"],
            "pa": overall["sample"]["pa"], "flag": overall["sample"]["flag"],
            "xwoba": overall["xwoba"], "xwoba_vs_LHP": vs_l["xwoba"], "xwoba_vs_RHP": vs_r["xwoba"],
            "obp": overall["obp"], "slg": overall["slg"], "k_pct": overall["k_pct"], "bb_pct": overall["bb_pct"],
            "starts_by_position": line["starts_by_position"], "sb": line["sb"],
            "sprint_speed": sd["sprint_speed_ft_s"], "outs_above_average": sd.get("outs_above_average"),
            "consecutive_starts": w["consecutive_starts"], "rest_suggested": w["rest_suggested"],
        })
    return sorted(out, key=lambda x: -(x["xwoba"] or 0))


def get_starter_options(game_pk: int, team_id: int) -> list[dict]:
    """Our team's possible starting pitchers for this game: every active pitcher who has started games,
    with days of rest, whether he is rested enough to start (4+ days), season line and results allowed.
    We may reorder our own rotation, so any rested, healthy starter is an option."""
    g = _game(game_pk, team_id)
    d = g["game_date"]
    status = bullpen.bullpen_status(team_id, d)
    out = []
    for s in status["starters"]:
        line = pitching.season_line(s["player_id"], d)
        allowed = pitching.pitcher_split(s["player_id"], d)
        out.append({
            "player_id": s["player_id"], "name": s["name"], "throws": s["throws"], "days_rest": s["days_rest"],
            "ready_to_start": s["ready_to_start"], "starts": line["starts"], "ip": line["ip"], "era": line["era"],
            "avg_innings_per_start": line["avg_innings_per_start"], "xwoba_allowed": allowed["xwoba"],
            "k_pct": allowed["k_pct"], "bb_pct": allowed["bb_pct"], "flag": allowed["sample"]["flag"],
        })
    return sorted(out, key=lambda x: (not x["ready_to_start"], x["xwoba_allowed"] or 1))


# ---------------------------------------------------------------------------
# Predictions (Scouts)
# ---------------------------------------------------------------------------

def predict_opponent_starter(game_pk: int, opponent_id: int) -> dict:
    """Predict who will start for the opponent, from their rotation order and rest (MLB's announced probable
    is not used). Returns the pick, a confidence label, the next most likely, and how the call was made.
    For 2026 games it was right about 75% of the time (87% within the top two). For 2027 games it is a
    projection from the closing 2026 rotation, so treat it as a best guess."""
    g = _game(game_pk, opponent_id)
    p = rotation.predict_starter(opponent_id, g["game_date"], g["game_number"])
    return {"predicted": p["predicted"], "confidence": p["confidence"], "probability": p.get("probability"),
            "next_most_likely": p["next_most_likely"],
            "method": p["method"], "rotation_cycle_length": p["cycle_length"]}


def predict_opponent_lineup(game_pk: int, opponent_id: int, vs_hand: str | None = None) -> dict:
    """Predict the opponent's starting nine (batting order and positions) from their recent lineups.
    vs_hand = the throwing hand of OUR starting pitcher ('L' or 'R'): teams platoon, so lineups against a
    lefty differ from lineups against a righty. Historically about 7.5 of 9 predicted starters are right."""
    if vs_hand not in (None, "L", "R"):
        raise ValueError("vs_hand must be 'L', 'R', or omitted.")
    g = _game(game_pk, opponent_id)
    return lineup.predict_lineup(opponent_id, g["game_date"], vs_hand)


def get_matchups(game_pk: int, pitcher_id: int, batter_ids: list[int]) -> list[dict]:
    """Score batters against one pitcher. For each batter: expected xwOBA built from the pitcher's pitch mix
    against that batter's side and how each does against fastballs / breaking / offspeed, compared to league
    average, plus who has the edge (batter / pitcher / even) and any small-sample warnings. Best for the
    batter first. Use it both ways: our hitters vs their starter, and their hitters vs our starter."""
    g = _game(game_pk)
    if not batter_ids:
        raise ValueError("Give at least one batter_id.")
    if len(batter_ids) > 15:
        raise ValueError("At most 15 batters per call.")
    for pid in [pitcher_id, *batter_ids]:
        if not roster.player_info(pid):
            raise ValueError(f"Unknown player_id {pid}.")
    return matchups.matchups(batter_ids, pitcher_id, g["game_date"])


def pitcher_role(player_id: int, game_date: str) -> dict:
    """Starts, saves and holds this season before the game (used by the checker)."""
    from backend import db
    r = db.one("SELECT SUM(is_starter) gs, SUM(sv) sv, SUM(hld) hld FROM pitching_lines WHERE player_id = ? "
               "AND game_date < ?", player_id, game_date)
    return {"starts": r["gs"] or 0, "saves": r["sv"] or 0, "holds": r["hld"] or 0}


def get_model_lineup(game_pk: int, team_id: int, pitcher_id: int, unavailable: set[int] | None = None) -> dict:
    """The lineup the win model rates best against this starter: nine players, positions and batting order that
    maximize expected runs (hitter xwOBA, his platoon split, the starter's quality and depth), with each player's
    runs per plate appearance, the rest-day decisions priced in win probability, and the bench ranked."""
    from backend.engine.winmodel import best_lineup

    g = _game(game_pk, team_id)
    if not roster.player_info(pitcher_id):
        raise ValueError(f"Unknown pitcher_id {pitcher_id}.")
    return best_lineup(team_id, g["game_date"], pitcher_id, set(unavailable or ()), home=g["home_team_id"] == team_id)


TOOLS = [get_game_context, get_roster_and_injuries, get_bullpen_status, get_hitter_profile, get_pitcher_profile,
         get_hitters_overview, get_starter_options, predict_opponent_starter, predict_opponent_lineup, get_matchups, get_model_lineup]
