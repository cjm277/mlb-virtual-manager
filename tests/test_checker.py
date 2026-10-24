"""The consistency checker catches broken plans (no LLM: plans are built by hand from real data)."""

import pytest

from backend import tools
from backend.checker import check_plan, ledger_numbers, supported
from backend.engine.lineup import predict_lineup
from backend.models import (BenchRole, BullpenRole, LineupPlan, LineupSpot, MedicalReport, PitchingPlan, PlayerRef,
                            PlayerStatus, PitchMixTarget, Scenario, StarterPlan, Substitution)

GAME, TOR, BOS, DATE = 824750, 141, 111, "2026-06-16"
CEASE, TOLLE = 656302, 801139
SCENARIOS = ["close_late_lead", "close_late_tied_or_trailing", "blowout_lead", "blowout_deficit",
             "starter_early_exit", "extra_innings"]


def good_lineup() -> LineupPlan:
    pred = predict_lineup(TOR, DATE, "L")
    spots = [LineupSpot(slot=p["slot"], player_id=p["player_id"], name=p["name"], position=p["position"],
                        bats=p["bats"], reason="r") for p in pred["lineup"]]
    bench = [BenchRole(player_id=b["player_id"], name=b["name"], role="utility", note="n") for b in pred["bench"]]
    subs = [Substitution(kind="pinch_hit", situation="late", bench_player_id=bench[0].player_id,
                         replaces_player_id=spots[-1].player_id, reason="r")]
    return LineupPlan(opposing_starter_assumed=PlayerRef(player_id=TOLLE, name="Payton Tolle"),
                      lineup=spots, bench=bench, substitutions=subs, summary="s")


def good_pitching() -> PitchingPlan:
    bp = tools.get_bullpen_status(GAME, TOR)
    pen = [BullpenRole(player_id=r["player_id"], name=r["name"], throws=r["throws"],
                       role="middle" if r["status"] != "unavailable" else "unavailable", note="n")
           for r in bp["relievers"]]
    usable = [b.player_id for b in pen if b.role != "unavailable"]
    return PitchingPlan(
        starter=StarterPlan(player_id=CEASE, name="Dylan Cease", throws="R", reason="r", expected_innings=6,
                            pitch_count_limit=100,
                            pitch_mix=[PitchMixTarget(pitch="slider", vs_lhb_pct=50, vs_rhb_pct=50, purpose="p"),
                                       PitchMixTarget(pitch="4-seam", vs_lhb_pct=50, vs_rhb_pct=50, purpose="p")],
                            keys=["k"]),
        bullpen=pen, scenarios=[Scenario(scenario=s, plan="p", pitcher_ids=usable[:2]) for s in SCENARIOS],
        summary="s")


def run(**overrides):
    parts = dict(medical=MedicalReport(statuses=[], summary="s"), scout_pitchers=None, scout_hitters=None,
                 pitching=good_pitching(), lineup=good_lineup(), ledger=[])
    parts.update(overrides)
    return check_plan(GAME, TOR, BOS, **parts)


def codes(issues):
    return {i.code for i in issues}


def test_a_legal_plan_passes():
    assert run() == []


def test_two_players_at_one_position():
    lu = good_lineup()
    catcher = next(s for s in lu.lineup if s.position == "C")
    other = next(s for s in lu.lineup if s.position == "LF")
    other.position = catcher.position
    assert "positions" in codes(run(lineup=lu))


def test_player_ruled_out_by_the_doctor_cannot_start():
    lu = good_lineup()
    victim = lu.lineup[0]
    med = MedicalReport(statuses=[PlayerStatus(player_id=victim.player_id, name=victim.name, status="out",
                                               reason="test")], summary="s")
    issues = run(lineup=lu, medical=med)
    assert any(i.code == "unavailable_starter" and victim.name in i.message for i in issues)


def test_injured_list_player_cannot_start():
    lu = good_lineup()
    lu.lineup[0].player_id, lu.lineup[0].name = 662139, "Daulton Varsho"   # on the 10-day IL that day
    assert "unavailable_starter" in codes(run(lineup=lu))


def test_starter_cannot_also_be_in_the_bullpen():
    p = good_pitching()
    p.bullpen.append(BullpenRole(player_id=CEASE, name="Dylan Cease", throws="R", role="long", note="n"))
    assert "starter_in_bullpen" in codes(run(pitching=p))


def test_unrested_starter_is_rejected():
    p = good_pitching()
    p.starter.player_id, p.starter.name = 702056, "Trey Yesavage"            # 3 days of rest that day
    assert "starter_not_rested" in codes(run(pitching=p))


def test_scenarios_cannot_use_a_pitcher_without_a_bullpen_role():
    p = good_pitching()
    p.scenarios[0].pitcher_ids = [CEASE]
    assert "starter_in_scenario" in codes(run(pitching=p))


def test_pinch_hitter_must_come_from_the_bench():
    lu = good_lineup()
    lu.substitutions[0].bench_player_id = lu.lineup[0].player_id
    assert "sub_not_on_bench" in codes(run(lineup=lu))


def test_lineup_must_face_the_starter_the_scouts_expect():
    from backend.models import PitchersScoutingReport, StarterPrediction
    scout = PitchersScoutingReport(
        opposing_starter=StarterPrediction(player_id=TOLLE, name="Payton Tolle", throws="L", confidence="high"),
        arsenal=[], how_to_attack=[], best_matchups=[], toughest_matchups=[], bullpen_to_watch=[], summary="s")
    lu = good_lineup()
    lu.opposing_starter_assumed = PlayerRef(player_id=CEASE, name="Dylan Cease")
    assert "wrong_opposing_starter" in codes(run(lineup=lu, scout_pitchers=scout))


def test_every_quoted_stat_must_come_from_a_tool():
    profile = tools.get_pitcher_profile(GAME, CEASE)
    whiff = next(a["whiff_pct"] for a in profile["arsenal"] if a["code"] == "SL")
    p = good_pitching()
    p.summary = f"His slider gets a {whiff}% whiff rate."
    assert run(pitching=p, ledger=[profile]) == []                       # copied from a tool: fine
    p.summary = "His slider gets a 61.3% whiff rate and hitters have a .118 xwOBA."
    issues = run(pitching=p, ledger=[profile])
    assert codes(issues) == {"unsupported_number"} and "61.3" in issues[0].message


@pytest.mark.parametrize("claim, ok", [("0.346", True), (".346", True), ("0.35", True), ("0.347", False)])
def test_number_matching_respects_rounding(claim, ok):
    assert supported(claim, ledger_numbers([{"expected_xwoba": 0.346}])) is ok
