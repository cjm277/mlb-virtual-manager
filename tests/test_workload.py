"""The rest-day rule: straight starts are counted correctly, the thresholds apply by position, 2027 is exempt."""

from backend import db
from backend.engine.workload import REST_AFTER, consecutive_starts, rest_check

NYY, BELLINGER, DATE = 147, 641355, "2026-09-10"


def test_consecutive_starts_match_the_box_scores():
    run = consecutive_starts(NYY, BELLINGER, DATE)
    last = db.rows("""SELECT DISTINCT game_pk, game_date FROM batting_lines WHERE team_id = ? AND game_date < ?
                      ORDER BY game_date DESC, game_pk DESC LIMIT ?""", NYY, DATE, run + 1)
    started = {r["game_pk"] for r in db.rows(
        "SELECT game_pk FROM batting_lines WHERE player_id = ? AND is_starter = 1", BELLINGER)}
    assert all(g["game_pk"] in started for g in last[:run])          # started each of the last `run` games
    assert len(last) == run or last[run]["game_pk"] not in started   # and not the one before them


def test_rest_suggested_at_the_position_threshold():
    run = consecutive_starts(NYY, BELLINGER, DATE)
    assert rest_check(NYY, BELLINGER, DATE, "LF")["rest_suggested"] == (run >= REST_AFTER["other"])
    assert rest_check(NYY, BELLINGER, DATE, "C")["rest_suggested"] == (run >= REST_AFTER["C"])
    assert REST_AFTER["C"] < REST_AFTER["other"]                       # catchers need days off sooner


def test_no_workload_rule_before_any_2027_game_is_played():
    r = rest_check(NYY, BELLINGER, "2027-05-03", "LF")
    assert r["rest_suggested"] is False and r["consecutive_starts"] is None


def test_code_adds_a_rest_flag_the_doctor_missed():
    from backend import tools
    from backend.agents.team import stamp_rest_days
    from backend.models import MedicalReport
    ctx = tools.get_game_context(823499, NYY)          # NYY vs COL, 2026-09-10
    report = MedicalReport(statuses=[], summary="All clear.")
    stamp_rest_days(report, ctx)
    assert any(s.player_id == BELLINGER and s.status == "rest_suggested" for s in report.statuses)
    stamp_rest_days(report, ctx)                         # idempotent: never listed twice
    assert sum(s.player_id == BELLINGER for s in report.statuses) == 1


def test_a_tired_hitter_is_never_out_and_the_manager_can_start_him():
    import json
    from pathlib import Path
    from backend import tools
    from backend.agents.team import stamp_rest_days
    from backend.checker import check_plan
    from backend.models import LineupPlan, MedicalReport, PlayerStatus
    ctx = tools.get_game_context(823499, NYY)
    # The Doctor wrongly marks the tired Bellinger "out": code turns it back into a rest suggestion.
    report = MedicalReport(statuses=[PlayerStatus(player_id=BELLINGER, name="Cody Bellinger", status="out",
                                                  reason="Tired.")], summary="s")
    stamp_rest_days(report, ctx)
    assert [s.status for s in report.statuses if s.player_id == BELLINGER] == ["rest_suggested"]
    # And a lineup that starts him (the manager overriding the rest day) passes the checker.
    saved = Path(__file__).resolve().parents[1] / "evidence" / "logs" / "phase7_rest_rule_run"
    plan = json.loads((saved / "plan.json").read_text(encoding="utf-8"))
    lineup = LineupPlan.model_validate(plan["sections"]["lineup_card"])
    assert BELLINGER in {s.player_id for s in lineup.lineup}
    issues = check_plan(823499, NYY, ctx["opponent_id"], medical=report, scout_pitchers=None, scout_hitters=None,
                        pitching=None, lineup=lineup, ledger=json.loads((saved / "ledger.json").read_text(encoding="utf-8")))
    assert not any(i.code == "unavailable_starter" for i in issues)
