"""Typed outputs for every element of the game plan.

Each agent must return exactly one of these. The consistency checker reads the typed fields
(player ids, positions, roles), so a plan is checked by code, not by trusting the text.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Position = Literal["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]
Hand = Literal["L", "R", "S"]
Edge = Literal["batter", "pitcher", "even"]


class PlayerRef(BaseModel):
    player_id: int
    name: str


# --- Team Doctor ----------------------------------------------------------------

class PlayerStatus(BaseModel):
    player_id: int
    name: str
    status: Literal["out", "limited", "cleared_with_caution"]
    reason: str = Field(description="Taken from the tool output (injury text, workload rule, or health note).")


class MedicalReport(BaseModel):
    statuses: list[PlayerStatus] = Field(description="Only players who are NOT fully available.")
    summary: str = Field(description="2-3 sentences for the coaching staff.")


# --- Scouts ---------------------------------------------------------------------

class StarterPrediction(BaseModel):
    player_id: int
    name: str
    throws: Literal["L", "R"]
    confidence: str
    alternatives: list[str] = []


class PitchNote(BaseModel):
    pitch: str
    usage_pct: float
    velo: float | None = None
    whiff_pct: float | None = None
    note: str


class MatchupNote(BaseModel):
    player_id: int
    name: str
    expected_xwoba: float
    edge: Edge
    note: str


class RelieverNote(BaseModel):
    player_id: int
    name: str
    throws: Literal["L", "R"]
    note: str


class PitchersScoutingReport(BaseModel):
    """Opposing pitchers, written for OUR hitters."""
    opposing_starter: StarterPrediction
    arsenal: list[PitchNote]
    how_to_attack: list[str] = Field(description="3-5 short, concrete points for our hitters.")
    best_matchups: list[MatchupNote] = Field(description="Our 3-4 hitters with the best matchup vs their starter.")
    toughest_matchups: list[MatchupNote] = Field(description="Our 2-3 hitters with the toughest matchup.")
    bullpen_to_watch: list[RelieverNote] = Field(description="Up to 4 opposing relievers likely to matter.")
    summary: str


class LineupEntry(BaseModel):
    slot: int
    player_id: int
    name: str
    position: Position
    bats: Hand


class OpposingHitter(BaseModel):
    player_id: int
    name: str
    bats: Hand
    threat: Literal["high", "medium", "low"]
    xwoba: float | None = None
    weakness: str
    how_to_pitch: str


class HittersScoutingReport(BaseModel):
    """Opposing hitters, written for OUR pitchers."""
    lineup_vs_rhp: list[LineupEntry] = Field(description="Their expected lineup if we start a right-hander.")
    lineup_vs_lhp: list[LineupEntry] = Field(description="Their expected lineup if we start a left-hander.")
    hitters: list[OpposingHitter] = Field(description="One entry per hitter who appears in either lineup.")
    summary: str


# --- Pitching Coach -----------------------------------------------------------------

class PitchMixTarget(BaseModel):
    pitch: str
    vs_lhb_pct: float
    vs_rhb_pct: float
    purpose: str


class StarterPlan(BaseModel):
    player_id: int
    name: str
    throws: Literal["L", "R"]
    reason: str
    expected_innings: float
    pitch_count_limit: int
    pitch_mix: list[PitchMixTarget]
    keys: list[str] = Field(description="3-4 points on attacking their lineup.")


class BullpenRole(BaseModel):
    player_id: int
    name: str
    throws: Literal["L", "R"]
    role: Literal["closer", "setup", "middle", "long", "lefty_specialist", "mop_up", "unavailable"]
    note: str


class Scenario(BaseModel):
    scenario: Literal["close_late_lead", "close_late_tied_or_trailing", "blowout_lead", "blowout_deficit",
                      "starter_early_exit", "extra_innings"]
    plan: str
    pitcher_ids: list[int] = Field(description="Relievers to use, in order.")


class PitchingPlan(BaseModel):
    starter: StarterPlan
    bullpen: list[BullpenRole]
    scenarios: list[Scenario]
    summary: str


# --- Bench Coach -----------------------------------------------------------------

class LineupSpot(BaseModel):
    slot: int
    player_id: int
    name: str
    position: Position
    bats: Hand
    reason: str


class BenchRole(BaseModel):
    player_id: int
    name: str
    role: Literal["pinch_hitter", "pinch_runner", "defensive_replacement", "backup_catcher", "utility"]
    note: str


class Substitution(BaseModel):
    kind: Literal["pinch_hit", "pinch_run", "defensive"]
    situation: str
    bench_player_id: int
    replaces_player_id: int
    reason: str


class LineupPlan(BaseModel):
    opposing_starter_assumed: PlayerRef
    lineup: list[LineupSpot] = Field(description="Exactly 9 spots: batting order with fielding positions.")
    bench: list[BenchRole]
    substitutions: list[Substitution]
    summary: str


# --- Manager --------------------------------------------------------------------

class FixInstruction(BaseModel):
    to: Literal["pitching_coach", "bench_coach", "scout_pitchers", "scout_hitters"]
    instruction: str


class ManagerReview(BaseModel):
    approved: bool
    fixes: list[FixInstruction] = Field(description="Empty if approved.")
    key_decisions: list[str] = Field(description="The 3-5 biggest calls in this plan and why.")
    keys_to_the_game: list[str] = Field(description="3-5 keys to winning this game.")
    summary: str


# --- Clubhouse Comms -------------------------------------------------------------

class Briefing(BaseModel):
    audience: Literal["hitters", "pitchers", "coaches"]
    headline: str
    message: str = Field(description="Under 150 words.")
    reminders: list[str]


class CommsPackage(BaseModel):
    briefings: list[Briefing] = Field(description="Exactly one each for hitters, pitchers, and coaches.")
