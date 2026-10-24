"""Planning 2027 games: published schedule, historical stats only, end-of-2026 rosters."""

from backend import db, tools
from backend.engine import games, hitting, roster
from backend.engine.common import is_future
from backend.engine.rotation import predict_starter, projected_rotation

TOR, BOS = 141, 111
VLADDY = 665489
GAME_2027 = 854184       # TOR @ BOS, 2027-05-03


def test_2027_schedule_is_loaded():
    n, first, last = db.one("SELECT COUNT(*), MIN(game_date), MAX(game_date) FROM future_games")
    assert n == 2430 and first.startswith("2027-03") and last.startswith("2027-09")
    seasons = {g["season"] for g in games.games_between(TOR, BOS)}
    assert seasons == {2026, 2027}


def test_2027_context_says_what_the_plan_is_built_on():
    ctx = tools.get_game_context(GAME_2027, TOR)
    assert ctx["season"] == 2027 and is_future(ctx["game_date"])
    assert "Full 2026 season" in ctx["stats_basis"]
    assert "end of the 2026 season" in ctx["roster_basis"]
    assert "team_2026_final_record" in ctx


def test_2027_stats_are_the_full_2026_season():
    split = hitting.batter_split(VLADDY, "2027-05-03")
    official_pa = db.one("SELECT pa FROM season_hitting WHERE season = 2026 AND player_id = ?", VLADDY)[0]
    assert split["sample"]["pa_2026"] == official_pa
    assert split["sample"]["weight_2025"] == "0%"
    assert "note" in hitting.recent_form(VLADDY, "2027-05-03")   # no 2027 games yet


def test_2027_roster_is_end_of_2026_plus_returning_injured():
    final_day = roster.roster_date(TOR, "2027-05-03")
    assert final_day.startswith("2026-09")
    players = roster.active_roster(TOR, "2027-05-03")
    flagged = [p for p in players if p.get("health_note")]
    assert flagged and all("Assumed healthy" in p["health_note"] for p in flagged)
    assert roster.unavailable_list(TOR, "2027-05-03") == []
    # Everyone flagged really did end 2026 on a list rather than the active roster.
    final = {p["player_id"] for p in roster._roster_on(TOR, final_day)}
    assert not {p["player_id"] for p in flagged} & final


def test_2027_rotation_projection_cycles_through_the_schedule():
    rot = projected_rotation(BOS)
    assert 5 <= len(rot) <= 6
    team_games = db.rows("""SELECT game_date, game_number FROM future_games WHERE home_team_id = ?1 OR away_team_id = ?1
                            ORDER BY game_date, game_number LIMIT ?2""", BOS, 2 * len(rot))
    picks = [predict_starter(BOS, g["game_date"], g["game_number"])["predicted"]["player_id"] for g in team_games]
    assert picks[: len(rot)] == rot            # Opening Day starts the workhorse, then in order
    assert picks[len(rot):] == rot             # and the cycle repeats


def test_2027_everyone_starts_rested():
    status = tools.get_bullpen_status(GAME_2027, TOR)
    assert all(s["ready_to_start"] for s in status["starters"])
    assert all(r["status"] == "available" for r in status["relievers"])


def test_2026_games_are_unchanged():
    assert not is_future("2026-09-27")
    assert tools.predict_opponent_starter(824750, BOS)["predicted"]["name"] == "Payton Tolle"
