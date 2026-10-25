"""The win-model lineup: always legal, never uses an unavailable player, rests tired hitters only on cheap days,
and the matchup score keeps only the measured share of its pitch-type detail. No LLM."""

import pytest

from backend import tools
from backend.engine import matchups, winmodel
from backend.engine.matchups import matchup

GAME, TOR = 824957, 141            # TOR @ ATH, 2026-09-08
DATE, PERKINS = "2026-09-08", 678022
VLADDY = 665489


def test_model_lineup_is_legal_and_ordered_by_value():
    r = tools.get_model_lineup(GAME, TOR, PERKINS)
    spots = r["lineup"]
    assert [s["slot"] for s in spots] == list(range(1, 10))
    assert sorted(s["position"] for s in spots) == sorted(winmodel.POSITIONS)
    assert len({s["player_id"] for s in spots}) == 9
    values = [s["runs_per_pa_vs_avg"] for s in spots]
    assert values == sorted(values, reverse=True)                 # best hitters bat most
    for s in spots:                                                # everyone plays a position he has played
        assert s["position"] in winmodel.eligible_positions(s["player_id"], DATE)


def test_model_lineup_never_uses_an_unavailable_player():
    first = tools.get_model_lineup(GAME, TOR, PERKINS)["lineup"][0]["player_id"]
    r = tools.get_model_lineup(GAME, TOR, PERKINS, {first})
    assert first not in {s["player_id"] for s in r["lineup"]}


def test_tired_hitters_rest_only_when_it_is_cheap(monkeypatch):
    r = tools.get_model_lineup(GAME, TOR, PERKINS)
    assert r["rest_decisions"]                                     # Toronto had tired regulars that day
    monkeypatch.setattr(winmodel, "REST_MAX_COST", 0.0)            # never worth it -> nobody sits for rest
    plays = tools.get_model_lineup(GAME, TOR, PERKINS)
    assert all(": plays;" in note for note in plays["rest_decisions"] if "catch today" not in note)


def test_matchup_score_keeps_only_the_measured_pitch_type_share(monkeypatch):
    raw = matchup(VLADDY, PERKINS, DATE, weight=1.0)
    none = matchup(VLADDY, PERKINS, DATE, weight=0.0)
    half = matchup(VLADDY, PERKINS, DATE, weight=0.5)
    assert half["expected_xwoba"] == pytest.approx((raw["expected_xwoba"] + none["expected_xwoba"]) / 2, abs=0.0011)
    assert raw["by_pitch_group"] == none["by_pitch_group"]          # the scouting detail is kept either way
    assert 0.0 <= matchups.pitch_type_weight() <= 1.0


# --- Defense -------------------------------------------------------------------------------------------------

from backend import db  # noqa: E402
from backend.engine import defense  # noqa: E402


def test_defense_never_looks_ahead():
    """A 2026 game only sees 2023-2025 ratings: a fielder whose only record at a position is from 2026 is rated
    like any player new to it, not by what he went on to do in 2026."""
    r = db.one("""SELECT f.player_id, f.position FROM fielding_by_position f
                  WHERE f.season = 2026 AND f.innings > 300 AND f.fielding_runs_prevented >= 5
                    AND NOT EXISTS (SELECT 1 FROM fielding_by_position h WHERE h.player_id = f.player_id
                                    AND h.position = f.position AND h.season < 2026 AND h.innings > 0) LIMIT 1""")
    assert r, "expected at least one fielder rated only in 2026"
    value = defense.fielding_per_game(r["player_id"], r["position"], defense.rating_season("2026-08-01"))
    s = defense.rating_settings()
    assert value in (s["new_position_per_game"], s["no_history_per_game"])


def test_dh_has_no_defense_and_catchers_are_rated_on_framing():
    kirk = 672386
    assert defense.runs_saved(kirk, "DH", DATE) == 0.0
    assert defense.runs_saved(kirk, "C", DATE) == defense.weights()["framing"] * defense.framing_per_game(kirk, 2025)


def test_model_lineup_counts_defense():
    r = tools.get_model_lineup(GAME, TOR, PERKINS)
    assert r["defense_runs_saved_per_game"] == pytest.approx(sum(s["defense_runs_per_game"] for s in r["lineup"]), abs=0.02)
    dh = next(s for s in r["lineup"] if s["position"] == "DH")
    assert dh["defense_runs_per_game"] == 0.0


# --- Marcel projection and the catcher workload cap --------------------------------------------------------------

def test_marcel_pools_2025_so_a_strong_track_record_is_not_pulled_to_average():
    """By August the old fade gave 2025 no weight; Marcel keeps it (weight 0.75), so Vladdy's value moves up."""
    winmodel.set_version("fade")
    old = winmodel.hitter_value(VLADDY, "2026-08-12")
    winmodel.set_version("marcel")
    new = winmodel.hitter_value(VLADDY, "2026-08-12")
    assert winmodel.params()["version"] == "marcel" and new > old


def test_catcher_cap_keeps_a_tired_catcher_from_catching():
    d, team = "2026-08-12", TOR
    recent = winmodel.recent_catcher_starts(team, d)
    sp = PERKINS
    capped = {p for p, n in recent.items() if n >= winmodel.CATCHER_MAX_STARTS}
    lineup = winmodel.best_lineup(team, d, sp)["lineup"]
    catcher = next(x["player_id"] for x in lineup if x["position"] == "C")
    assert catcher not in capped
    free = winmodel.best_lineup(team, d, sp, catcher_recent={})["lineup"]       # no history: no cap applies
    assert any(x["position"] == "C" for x in free)


def test_cautious_pricing_never_amplifies_a_thin_record(monkeypatch):
    """The optimizer prices a fielder at E[result | rating, experience group] fitted on 2025 (slope capped at 1); the
    verification lenses keep the raw rating."""
    cal = defense._params()["defense_caution"]
    assert all(c["slope"] <= 1.0 for c in cal.values())
    pid, pos = next((r["player_id"], r["position"]) for r in db.rows(
        """SELECT player_id, position FROM fielding_by_position WHERE season = 2025 AND innings BETWEEN 20 AND 250
           AND position NOT IN ('C', 'DH', 'P') AND fielding_runs_prevented > 1""")
        if defense.experience_group(r["player_id"], r["position"], 2025) == "part-time")
    raw = defense.runs_saved(pid, pos, DATE)
    monkeypatch.setattr(defense, "CAUTION", "calibrated")
    c = cal["part-time"]
    assert defense.runs_saved(pid, pos, DATE, priced=True) == pytest.approx(c["intercept"] + c["slope"] * raw)
    monkeypatch.setattr(defense, "CAUTION", "strict")
    assert defense.runs_saved(pid, pos, DATE, priced=True) == pytest.approx(c["mean"])
    assert defense.runs_saved(pid, pos, DATE) == raw                       # lenses: unchanged
