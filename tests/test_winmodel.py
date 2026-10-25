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
    assert all(": plays;" in note for note in plays["rest_decisions"])


def test_matchup_score_keeps_only_the_measured_pitch_type_share(monkeypatch):
    raw = matchup(VLADDY, PERKINS, DATE, weight=1.0)
    none = matchup(VLADDY, PERKINS, DATE, weight=0.0)
    half = matchup(VLADDY, PERKINS, DATE, weight=0.5)
    assert half["expected_xwoba"] == pytest.approx((raw["expected_xwoba"] + none["expected_xwoba"]) / 2, abs=0.0011)
    assert raw["by_pitch_group"] == none["by_pitch_group"]          # the scouting detail is kept either way
    assert 0.0 <= matchups.pitch_type_weight() <= 1.0
