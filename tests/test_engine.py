"""The stats engine and agent tools against known 2026 facts (Blue Jays at Red Sox, June 16)."""

import json

import pytest

from backend import tools
from backend.engine import bullpen, hitting, lineup, matchups, roster

GAME = 824750            # TOR @ BOS, 2026-06-16
TOR, BOS = 141, 111
VLADDY, CEASE, TOLLE, VARSHO = 665489, 656302, 801139, 662139
DATE = "2026-06-16"


def test_stats_stop_the_day_before_the_game():
    # Vladdy had 288 PA through June 15 (matches MLB's published line in the Phase 2 spot-checks).
    assert hitting.batter_split(VLADDY, DATE)["sample"]["pa_2026"] == 288
    # Asking about the next day adds exactly his June 16 plate appearances, no more.
    june16 = hitting.season_line(VLADDY, "2026-06-17")["pa"] - hitting.season_line(VLADDY, DATE)["pa"]
    assert 3 <= june16 <= 6


def test_no_2025_weight_by_june():
    assert hitting.batter_split(VLADDY, DATE)["sample"]["weight_2025"] == "0%"


def test_early_season_leans_on_2025():
    # April 5 is 11 days after Opening Day (March 25): 1 - 11/42 = 74% on 2025.
    early = hitting.batter_split(VLADDY, "2026-04-05")["sample"]
    assert early["pa_2026"] > 0
    assert early["weight_2025"] == "74%"
    assert early["pa_2025"] == 680


def test_before_a_players_first_2026_game_it_is_all_2025():
    # The Jays had not played yet on March 26, so there is nothing from 2026 to blend in.
    early = hitting.batter_split(VLADDY, "2026-03-26")["sample"]
    assert early["pa_2026"] == 0
    assert early["weight_2025"] == "100%"


def test_injured_player_is_listed_with_reason_and_not_active():
    out = {p["player_id"]: p for p in roster.unavailable_list(TOR, DATE)}
    assert out[VARSHO]["list"] == "10-day injured list"
    assert "wrist" in out[VARSHO]["reason"].lower()
    assert VARSHO not in {r["player_id"] for r in roster.active_roster(TOR, DATE)}


def test_rotation_predictor_names_the_starter_who_pitched():
    assert tools.predict_opponent_starter(GAME, BOS)["predicted"]["player_id"] == TOLLE


def test_starter_options_respect_rest():
    options = {o["player_id"]: o for o in tools.get_starter_options(GAME, TOR)}
    assert options[CEASE]["ready_to_start"] is True
    assert all(o["ready_to_start"] == (o["days_rest"] is None or o["days_rest"] >= 4) for o in options.values())


def test_predicted_lineup_is_a_legal_lineup():
    lu = lineup.predict_lineup(BOS, DATE, "R")["lineup"]
    assert len(lu) == 9
    assert len({p["player_id"] for p in lu}) == 9
    assert sorted(p["position"] for p in lu) == sorted(lineup.POSITIONS)
    active = {r["player_id"] for r in roster.active_roster(BOS, DATE)}
    assert all(p["player_id"] in active for p in lu)


@pytest.mark.parametrize("workload, status", [
    ({"consecutive_days": 3, "pitches_yesterday": 12, "pitches_last_3_days": 40}, "unavailable"),
    ({"consecutive_days": 1, "pitches_yesterday": 31, "pitches_last_3_days": 31}, "unavailable"),
    ({"consecutive_days": 2, "pitches_yesterday": 18, "pitches_last_3_days": 36}, "unavailable"),
    ({"consecutive_days": 1, "pitches_yesterday": 15, "pitches_last_3_days": 15}, "limited"),
    ({"consecutive_days": 0, "pitches_yesterday": 0, "pitches_last_3_days": 55}, "limited"),
    ({"consecutive_days": 0, "pitches_yesterday": 0, "pitches_last_3_days": 20}, "available"),
])
def test_bullpen_availability_rules(workload, status):
    assert bullpen.reliever_status(workload)[0] == status


def test_switch_hitters_bat_opposite_the_pitcher():
    assert matchups.batting_side("S", "R") == "L"
    assert matchups.batting_side("S", "L") == "R"
    assert matchups.batting_side("L", "L") == "L"


def test_matchup_platoon_and_flags():
    m = tools.get_matchups(GAME, TOLLE, [VLADDY])[0]   # righty hitter vs lefty pitcher
    assert m["platoon_advantage"] == "batter"
    assert m["edge"] in ("batter", "pitcher", "even")
    assert 0.1 < m["expected_xwoba"] < 0.6


def test_tools_reject_bad_inputs():
    with pytest.raises(ValueError, match="did not play"):
        tools.get_roster_and_injuries(GAME, 147)          # Yankees weren't in this game
    with pytest.raises(ValueError, match="Unknown player"):
        tools.get_hitter_profile(GAME, 1)
    with pytest.raises(ValueError, match="vs_hand"):
        tools.predict_opponent_lineup(GAME, BOS, "X")


def test_every_tool_returns_json():
    calls = [
        (tools.get_game_context, (GAME, TOR)), (tools.get_roster_and_injuries, (GAME, TOR)),
        (tools.get_bullpen_status, (GAME, TOR)), (tools.get_hitters_overview, (GAME, TOR)),
        (tools.get_starter_options, (GAME, TOR)), (tools.predict_opponent_starter, (GAME, BOS)),
        (tools.predict_opponent_lineup, (GAME, BOS, "R")), (tools.get_matchups, (GAME, TOLLE, [VLADDY])),
        (tools.get_hitter_profile, (GAME, VLADDY)), (tools.get_pitcher_profile, (GAME, CEASE)),
        (tools.get_model_lineup, (GAME, TOR, TOLLE)), (tools.get_model_starter, (GAME, TOR)),
    ]
    assert len(calls) == len(tools.TOOLS)
    for fn, args in calls:
        json.dumps(fn(*args))


def test_game_context_hides_the_final_score():
    ctx = tools.get_game_context(GAME, TOR)
    assert "home_score" not in ctx and "away_score" not in ctx
    assert ctx["home_away"] == "away" and ctx["opponent"] == "Boston Red Sox"
