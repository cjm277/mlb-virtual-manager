"""The agents' tools: thin wrappers over backend/tools.py, bound to the game being planned.

- The game and both team ids come from the run context, so an agent only says "us" or "opponent";
  it cannot point a tool at another game or date.
- Every result is written to the audit trail and added to the run's ledger. The consistency checker
  later verifies that every stat quoted in the plan appears in that ledger.
- A bad input becomes a ModelRetry: the agent sees the message and can correct itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic_ai import ModelRetry, RunContext

from backend import tools
from backend.audit import Audit, preview

Side = Literal["us", "opponent"]


@dataclass
class PlanDeps:
    game_pk: int
    team_id: int
    opponent_id: int
    game_date: str
    audit: Audit
    context: dict = field(default_factory=dict)
    notes: str | None = None
    agent: str = ""
    ledger: list[Any] = field(default_factory=list)


def _call(ctx: RunContext[PlanDeps], name: str, args: dict, fn: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    try:
        out = fn()
    except ValueError as exc:
        ctx.deps.audit.log("tool_error", agent=ctx.deps.agent, tool=name, args=args, error=str(exc))
        raise ModelRetry(str(exc)) from exc
    ctx.deps.ledger.append(out)
    ctx.deps.audit.log("tool_result", agent=ctx.deps.agent, tool=name, args=args,
                       ms=round(1000 * (time.perf_counter() - started)), result_chars=len(preview(out, 10**9)),
                       result=preview(out))
    return out


def _team(ctx: RunContext[PlanDeps], side: Side) -> int:
    return ctx.deps.team_id if side == "us" else ctx.deps.opponent_id


def game_context(ctx: RunContext[PlanDeps]) -> dict:
    """Facts about this game from our side: date, home/away, ballpark, records, and what the stats are based on."""
    d = ctx.deps
    return _call(ctx, "game_context", {}, lambda: tools.get_game_context(d.game_pk, d.team_id))


def roster_and_injuries(ctx: RunContext[PlanDeps], side: Side) -> dict:
    """Available hitters and pitchers (position, handedness) for 'us' or 'opponent', and who is out and why."""
    d = ctx.deps
    return _call(ctx, "roster_and_injuries", {"side": side},
                 lambda: tools.get_roster_and_injuries(d.game_pk, _team(ctx, side)))


def bullpen_status(ctx: RunContext[PlanDeps], side: Side) -> dict:
    """Every pitcher's recent workload for 'us' or 'opponent': relievers marked available / limited /
    unavailable by fixed rules, starters with days of rest."""
    d = ctx.deps
    return _call(ctx, "bullpen_status", {"side": side}, lambda: tools.get_bullpen_status(d.game_pk, _team(ctx, side)))


def hitters_overview(ctx: RunContext[PlanDeps], side: Side) -> list[dict]:
    """One row per available hitter for 'us' or 'opponent': xwOBA overall and vs LHP/RHP, OBP, SLG, K %, BB %,
    positions started, sprint speed, defense, sample flag. Cheaper than single profiles; call it first."""
    d = ctx.deps
    return _call(ctx, "hitters_overview", {"side": side},
                 lambda: tools.get_hitters_overview(d.game_pk, _team(ctx, side)))


def starter_options(ctx: RunContext[PlanDeps]) -> list[dict]:
    """Our possible starting pitchers: days of rest, ready to start (4+ days), season line, results allowed."""
    d = ctx.deps
    return _call(ctx, "starter_options", {}, lambda: tools.get_starter_options(d.game_pk, d.team_id))


def predict_opponent_starter(ctx: RunContext[PlanDeps]) -> dict:
    """Who the opponent will most likely start (rotation order and rest), with confidence and alternatives."""
    d = ctx.deps
    return _call(ctx, "predict_opponent_starter", {}, lambda: tools.predict_opponent_starter(d.game_pk, d.opponent_id))


def predict_opponent_lineup(ctx: RunContext[PlanDeps], vs_hand: Literal["L", "R"]) -> dict:
    """The opponent's likely starting nine (order and positions) against a starter who throws vs_hand."""
    d = ctx.deps
    return _call(ctx, "predict_opponent_lineup", {"vs_hand": vs_hand},
                 lambda: tools.predict_opponent_lineup(d.game_pk, d.opponent_id, vs_hand))


def hitter_profile(ctx: RunContext[PlanDeps], player_id: int) -> dict:
    """One hitter in depth: overall, vs LHP / RHP, vs fastballs / breaking / offspeed, recent form, speed, defense."""
    d = ctx.deps
    return _call(ctx, "hitter_profile", {"player_id": player_id}, lambda: tools.get_hitter_profile(d.game_pk, player_id))


def pitcher_profile(ctx: RunContext[PlanDeps], player_id: int) -> dict:
    """One pitcher in depth: season line, results vs LHB / RHB, full arsenal, and pitch mix by batter side."""
    d = ctx.deps
    return _call(ctx, "pitcher_profile", {"player_id": player_id},
                 lambda: tools.get_pitcher_profile(d.game_pk, player_id))


def matchups(ctx: RunContext[PlanDeps], pitcher_id: int, batter_ids: list[int]) -> list[dict]:
    """Score up to 15 batters against one pitcher: expected xwOBA vs league, who has the edge, and why."""
    d = ctx.deps
    return _call(ctx, "matchups", {"pitcher_id": pitcher_id, "batter_ids": batter_ids},
                 lambda: tools.get_matchups(d.game_pk, pitcher_id, batter_ids))


ALL_TOOLS = {f.__name__: f for f in (game_context, roster_and_injuries, bullpen_status, hitters_overview,
                                     starter_options, predict_opponent_starter, predict_opponent_lineup,
                                     hitter_profile, pitcher_profile, matchups)}
