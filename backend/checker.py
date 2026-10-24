"""Consistency checker: plain code that checks the agents' plan against the rules and the data.

Two kinds of checks:
1. Plan rules: a legal lineup (9 players, every position once), only available players, the fielders are
   the hitters in the batting order, the starter is rested and not in the bullpen plan, no unavailable
   relievers in any scenario, bench moves use bench players, and the lineup is built for the starter the
   scouts expect.
2. Numbers: every decimal stat quoted anywhere in a report must appear in a tool result from this run
   (the ledger). Planning targets the coaches set themselves (pitch-count limit, innings, mix targets)
   are not checked.

Each issue names the agent that owns it, so the fix loop knows who must correct it.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import BaseModel

from backend import tools
from backend.models import (HittersScoutingReport, LineupPlan, MedicalReport, PitchersScoutingReport, PitchingPlan)

POSITIONS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}
# Fields that hold the coaches' own planning targets, not stats.
NOT_STATS = {"expected_innings", "pitch_count_limit", "vs_lhb_pct", "vs_rhb_pct", "slot", "player_id",
             "bench_player_id", "replaces_player_id", "pitcher_ids"}
DECIMAL = re.compile(r"(?<![\w.])(\d*\.\d+)(?![\d])")


@dataclass
class Issue:
    owner: str
    code: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Number verification
# ---------------------------------------------------------------------------

def _numbers_in(value: Any, out: set[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.add(float(value))
    elif isinstance(value, dict):
        for v in value.values():
            _numbers_in(v, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _numbers_in(v, out)
    elif isinstance(value, str):
        for m in DECIMAL.findall(value):
            out.add(float(m))


def ledger_numbers(ledger: list[Any]) -> set[float]:
    nums: set[float] = set()
    _numbers_in(ledger, nums)
    return nums


def _claims(model: BaseModel) -> list[tuple[str, str]]:
    """(field path, decimal as written) for every decimal stat in typed fields and in text."""
    found: list[tuple[str, str]] = []

    def walk(value: Any, path: str) -> None:
        key = path.rsplit(".", 1)[-1].split("[")[0]
        if key in NOT_STATS:
            return
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                walk(getattr(value, name), f"{path}.{name}" if path else name)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{path}[{i}]")
        elif isinstance(value, float):
            found.append((path, repr(value)))
        elif isinstance(value, str):
            found.extend((path, m) for m in DECIMAL.findall(value))

    walk(model, "")
    return found


def supported(claim: str, ledger_nums: set[float]) -> bool:
    places = len(claim.split(".")[1]) if "." in claim else 0
    value = float(claim)
    places = min(places, 3)
    return any(round(n, places) == round(value, places) for n in ledger_nums)


def check_numbers(owner: str, model: BaseModel, ledger_nums: set[float]) -> list[Issue]:
    bad = [(path, c) for path, c in _claims(model) if not supported(c, ledger_nums)]
    if not bad:
        return []
    shown = "; ".join(f"{c} in {p}" for p, c in bad[:6])
    return [Issue(owner, "unsupported_number",
                  f"{len(bad)} number(s) do not appear in any tool result: {shown}. "
                  "Copy stats exactly from tool results or remove them.")]


# ---------------------------------------------------------------------------
# Plan rules
# ---------------------------------------------------------------------------

def _doctor_out(medical: MedicalReport | None) -> set[int]:
    return {s.player_id for s in medical.statuses if s.status == "out"} if medical else set()


def check_plan(game_pk: int, team_id: int, opponent_id: int, *, medical: MedicalReport | None,
               scout_pitchers: PitchersScoutingReport | None, scout_hitters: HittersScoutingReport | None,
               pitching: PitchingPlan | None, lineup: LineupPlan | None, ledger: list[Any]) -> list[Issue]:
    issues: list[Issue] = []
    g = tools.get_game_context(game_pk, team_id)
    ours = tools.get_roster_and_injuries(game_pk, team_id)
    theirs = tools.get_roster_and_injuries(game_pk, opponent_id)
    out = _doctor_out(medical)
    our_hitters = {p["player_id"] for p in ours["hitters"]} - out
    our_pitchers = {p["player_id"] for p in ours["pitchers"]} - out
    their_hitters = {p["player_id"] for p in theirs["hitters"]}
    their_pitchers = {p["player_id"] for p in theirs["pitchers"]}
    names = {p["player_id"]: p["name"] for p in ours["hitters"] + ours["pitchers"] + theirs["hitters"] + theirs["pitchers"]}

    def name_ok(owner: str, pid: int, name: str, where: str) -> None:
        real = names.get(pid)
        if real and real.split()[-1].lower() not in name.lower():
            issues.append(Issue(owner, "name_mismatch", f"{where}: player_id {pid} is {real}, not '{name}'."))

    # Team Doctor ------------------------------------------------------------------
    if medical:
        everyone = {p["player_id"] for p in ours["hitters"] + ours["pitchers"]} | {o["player_id"] for o in ours["out"]}
        for s in medical.statuses:
            if s.player_id not in everyone:
                issues.append(Issue("team_doctor", "unknown_player", f"{s.name} ({s.player_id}) is not on our team."))

    # Scout: opposing pitchers ---------------------------------------------------------
    if scout_pitchers:
        sp = scout_pitchers.opposing_starter
        if sp.player_id not in their_pitchers:
            issues.append(Issue("scout_pitchers", "bad_opposing_starter",
                                f"{sp.name} ({sp.player_id}) is not an available pitcher for {g['opponent']}."))
        for m in scout_pitchers.best_matchups + scout_pitchers.toughest_matchups:
            if m.player_id not in our_hitters:
                issues.append(Issue("scout_pitchers", "unavailable_hitter",
                                    f"Matchup note for {m.name} ({m.player_id}), who is not one of our available hitters."))
        for r in scout_pitchers.bullpen_to_watch:
            if r.player_id not in their_pitchers:
                issues.append(Issue("scout_pitchers", "bad_reliever", f"{r.name} ({r.player_id}) is not on their staff."))

    # Scout: opposing hitters ------------------------------------------------------------
    if scout_hitters:
        for label, lu in (("lineup_vs_rhp", scout_hitters.lineup_vs_rhp), ("lineup_vs_lhp", scout_hitters.lineup_vs_lhp)):
            ids = [e.player_id for e in lu]
            if len(lu) != 9 or len(set(ids)) != 9:
                issues.append(Issue("scout_hitters", "bad_opposing_lineup", f"{label} must list 9 different players."))
            if {e.position for e in lu} != POSITIONS:
                issues.append(Issue("scout_hitters", "bad_opposing_lineup", f"{label} must use each position once."))
            stray = [e.name for e in lu if e.player_id not in their_hitters]
            if stray:
                issues.append(Issue("scout_hitters", "bad_opposing_lineup",
                                    f"{label} includes players not available to {g['opponent']}: {', '.join(stray)}."))

    # Pitching Coach ---------------------------------------------------------------------
    if pitching:
        st = pitching.starter
        options = {o["player_id"]: o for o in tools.get_starter_options(game_pk, team_id)}
        if st.player_id not in our_pitchers:
            issues.append(Issue("pitching_coach", "starter_unavailable",
                                f"Starter {st.name} ({st.player_id}) is not an available pitcher (roster or Team Doctor)."))
        elif st.player_id in options and not options[st.player_id]["ready_to_start"]:
            issues.append(Issue("pitching_coach", "starter_not_rested",
                                f"Starter {st.name} has {options[st.player_id]['days_rest']} days of rest; 4+ needed."))
        name_ok("pitching_coach", st.player_id, st.name, "starter")
        for side in ("vs_lhb_pct", "vs_rhb_pct"):
            total = sum(getattr(m, side) for m in st.pitch_mix)
            if not 95 <= total <= 105:
                issues.append(Issue("pitching_coach", "pitch_mix_total",
                                    f"Pitch-mix targets {side} add up to {total:.0f}%, not about 100%."))
        bp = tools.get_bullpen_status(game_pk, team_id)
        unavailable = {r["player_id"] for r in bp["relievers"] if r["status"] == "unavailable"} | out
        roles = {}
        for r in pitching.bullpen:
            roles[r.player_id] = r.role
            if r.player_id == st.player_id:
                issues.append(Issue("pitching_coach", "starter_in_bullpen", f"{r.name} is the starter and also in the bullpen plan."))
            elif r.player_id not in our_pitchers | out:
                issues.append(Issue("pitching_coach", "unknown_reliever", f"{r.name} ({r.player_id}) is not on our staff."))
            elif r.player_id in unavailable and r.role != "unavailable":
                issues.append(Issue("pitching_coach", "unavailable_reliever",
                                    f"{r.name} is unavailable (workload rules or Team Doctor) but has role '{r.role}'."))
            name_ok("pitching_coach", r.player_id, r.name, "bullpen")
        for s in pitching.scenarios:
            for pid in s.pitcher_ids:
                if pid == st.player_id:
                    issues.append(Issue("pitching_coach", "starter_in_scenario", f"Scenario {s.scenario} uses the starter."))
                elif pid in unavailable or roles.get(pid) == "unavailable":
                    issues.append(Issue("pitching_coach", "unavailable_in_scenario",
                                        f"Scenario {s.scenario} uses unavailable pitcher {names.get(pid, pid)}."))
                elif pid not in roles:
                    issues.append(Issue("pitching_coach", "scenario_pitcher_not_in_bullpen",
                                        f"Scenario {s.scenario} uses {names.get(pid, pid)}, who has no bullpen role."))
        missing = {"close_late_lead", "close_late_tied_or_trailing", "blowout_lead", "blowout_deficit",
                   "starter_early_exit", "extra_innings"} - {s.scenario for s in pitching.scenarios}
        if missing:
            issues.append(Issue("pitching_coach", "missing_scenarios", f"No plan for: {', '.join(sorted(missing))}."))

    # Bench Coach ------------------------------------------------------------------------
    if lineup:
        spots = lineup.lineup
        ids = [s.player_id for s in spots]
        if len(spots) != 9 or len(set(ids)) != 9:
            issues.append(Issue("bench_coach", "lineup_size", f"The lineup has {len(set(ids))} different players; it needs 9."))
        if sorted(s.slot for s in spots) != list(range(1, 10)):
            issues.append(Issue("bench_coach", "batting_order", "Batting-order slots must be 1 through 9, once each."))
        positions = [s.position for s in spots]
        if set(positions) != POSITIONS or len(positions) != 9:
            dupes = sorted({p for p in positions if positions.count(p) > 1})
            missing = sorted(POSITIONS - set(positions))
            issues.append(Issue("bench_coach", "positions",
                                f"Each position must be filled once. Duplicated: {dupes or 'none'}; missing: {missing or 'none'}."))
        for s in spots:
            if s.player_id not in our_hitters:
                why = "out per the Team Doctor" if s.player_id in out else "not an available hitter on our roster"
                issues.append(Issue("bench_coach", "unavailable_starter", f"{s.name} ({s.player_id}) is {why}."))
            name_ok("bench_coach", s.player_id, s.name, f"lineup slot {s.slot}")
        bench_ids = {b.player_id for b in lineup.bench}
        for b in lineup.bench:
            if b.player_id in ids:
                issues.append(Issue("bench_coach", "bench_in_lineup", f"{b.name} is both in the lineup and on the bench."))
            elif b.player_id not in our_hitters:
                issues.append(Issue("bench_coach", "unavailable_bench", f"{b.name} ({b.player_id}) is not an available hitter."))
        for sub in lineup.substitutions:
            if sub.bench_player_id not in bench_ids:
                issues.append(Issue("bench_coach", "sub_not_on_bench",
                                    f"Move '{sub.situation}' uses {names.get(sub.bench_player_id, sub.bench_player_id)}, "
                                    "who is not on the bench."))
            if sub.replaces_player_id not in ids:
                issues.append(Issue("bench_coach", "sub_replaces_non_starter",
                                    f"Move '{sub.situation}' replaces {names.get(sub.replaces_player_id, sub.replaces_player_id)}, "
                                    "who is not in the lineup."))
        if scout_pitchers and lineup.opposing_starter_assumed.player_id != scout_pitchers.opposing_starter.player_id:
            issues.append(Issue("bench_coach", "wrong_opposing_starter",
                                f"The lineup assumes {lineup.opposing_starter_assumed.name}, but the scouts expect "
                                f"{scout_pitchers.opposing_starter.name}."))

    # Numbers --------------------------------------------------------------------------
    nums = ledger_numbers(ledger)
    for owner, model in (("team_doctor", medical), ("scout_pitchers", scout_pitchers), ("scout_hitters", scout_hitters),
                         ("pitching_coach", pitching), ("bench_coach", lineup)):
        if model is not None:
            issues += check_numbers(owner, model, nums)
    return issues
