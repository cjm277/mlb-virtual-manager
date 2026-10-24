"""The 2025 fade and the rate math the agents rely on."""

from datetime import date

import pytest

from backend.engine.common import blend_rates, effective_n, prior_weight, rates, sample_flag

OPENING = date(2026, 3, 25)


@pytest.mark.parametrize("game_date, expected", [
    ("2026-03-25", 1.0),   # Opening Day: all 2025
    ("2026-04-15", 0.5),   # 3 weeks in: half and half
    ("2026-05-06", 0.0),   # 6 weeks in: all 2026
    ("2026-07-01", 0.0),   # stays at zero after
    ("2026-03-20", 1.0),   # before Opening Day: never above 100%
])
def test_prior_weight_fades_linearly_over_six_weeks(game_date, expected):
    assert prior_weight(game_date, OPENING) == pytest.approx(expected)


def test_prior_weight_one_week_in():
    assert prior_weight("2026-04-01", OPENING) == pytest.approx(1 - 7 / 42, abs=1e-4)


def test_blend_weights_each_stat():
    blended, w = blend_rates({"xwoba": 0.300}, {"xwoba": 0.400}, 0.25)
    assert w == 0.25
    assert blended["xwoba"] == pytest.approx(0.75 * 0.300 + 0.25 * 0.400)


def test_rookie_with_no_2025_uses_2026_only():
    blended, w = blend_rates({"xwoba": 0.310}, None, 0.9)
    assert w == 0.0
    assert blended["xwoba"] == 0.310


def test_no_2026_games_yet_uses_2025_only():
    blended, w = blend_rates(None, {"xwoba": 0.350}, 0.2)
    assert w == 1.0
    assert blended["xwoba"] == 0.350


def test_missing_stat_in_one_season_falls_back_to_the_other():
    blended, _ = blend_rates({"whiff_pct": None}, {"whiff_pct": 25.0}, 0.5)
    assert blended["whiff_pct"] == 25.0


def test_effective_sample_weights_each_season():
    assert effective_n(100, 600, 0.5) == 350
    assert effective_n(100, 600, 0.0) == 100


@pytest.mark.parametrize("n, flag", [(10, "small"), (59, "small"), (60, "moderate"), (199, "moderate"), (200, "ok")])
def test_sample_flags_for_plate_appearances(n, flag):
    assert sample_flag(n, "pa") == flag


def test_rates_from_counts():
    c = dict.fromkeys(["pitches", "swings", "whiffs", "called_strikes", "zone_pitches", "chase_swings", "bip",
                       "hard_hit", "barrels", "ev_n", "ev_sum", "pa", "ab", "h", "tb", "hr", "bb", "k", "hbp",
                       "sf", "woba_den", "woba_num", "xwoba_num", "rv_sum"], 0)
    c.update(pa=10, ab=8, h=2, tb=5, bb=1, hbp=1, k=3, woba_den=10, woba_num=3.2, xwoba_num=3.5,
             pitches=40, zone_pitches=20, swings=20, whiffs=5, chase_swings=6)
    r = rates(c)
    assert r["avg"] == pytest.approx(0.25)
    assert r["obp"] == pytest.approx(4 / 10)
    assert r["slg"] == pytest.approx(5 / 8)
    assert r["woba"] == pytest.approx(0.32)
    assert r["k_pct"] == pytest.approx(30.0)
    assert r["whiff_pct"] == pytest.approx(25.0)
    assert r["chase_pct"] == pytest.approx(30.0)   # 6 chases / 20 pitches outside the zone
    assert r["hard_hit_pct"] is None               # no balls in play: no rate, not zero
