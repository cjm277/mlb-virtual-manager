"""The season-aware starter rule (backend/engine/starter_rule.py)."""

from backend.engine import starter_rule as sr
from backend import tools

D = "2026-08-12"


def test_best_rested_starter_wins_when_under_his_cap():
    members = [1, 2, 3]
    last = {1: "2026-08-07", 2: "2026-08-08", 3: "2026-08-06"}      # 1 and 3 are on 4+ days of rest
    cost = {1: -0.6, 2: -0.9, 3: 0.3}
    c = sr.choose(members, last, {1: 10, 2: 10, 3: 10}, {1: 10.2, 2: 10.2, 3: 10.2}, cost, D)
    assert c["pick"] == 1                       # 2 is better but not rested; 1 beats 3
    assert c["on_turn"] == 3                    # longest rested


def test_cap_stops_the_ace_past_two_extra_starts():
    members = [1, 3]
    last = {1: "2026-08-07", 3: "2026-08-06"}
    cost = {1: -0.6, 3: 0.3}
    capped = sr.choose(members, last, {1: 13, 3: 8}, {1: 10.2, 3: 10.2}, cost, D)   # 13 + 1 > 10.2 + 2
    assert capped["pick"] == 3
    ok = sr.choose(members, last, {1: 11, 3: 8}, {1: 10.2, 3: 10.2}, cost, D)       # 11 + 1 <= 12.2
    assert ok["pick"] == 1


def test_never_short_rest():
    members = [1, 2]
    last = {1: "2026-08-08", 2: "2026-08-09"}                       # 3 and 2 days of rest
    c = sr.choose(members, last, {}, {1: 5.0, 2: 5.0}, {1: -1.0, 2: 0.0}, D)
    assert c["pick"] == c["on_turn"] == 1 and not c["allowed"]


def test_recommendation_for_a_real_game_is_a_ready_rotation_starter():
    r = sr.recommend(141, D)
    pick = r["recommended"]["player_id"]
    row = next(x for x in r["rotation"] if x["player_id"] == pick)
    assert row["rested"] and row["under_cap"]
    assert sr.recommend(141, "2027-04-10")["recommended"] is None     # 2027: no rotation history yet


def test_tool_excludes_players_the_doctor_lists_as_out():
    game = 824957                                                     # TOR @ ATH, 2026-09-08
    first = tools.get_model_starter(game, 141)["recommended"]["player_id"]
    again = tools.get_model_starter(game, 141, {first})["recommended"]
    assert again is None or again["player_id"] != first
