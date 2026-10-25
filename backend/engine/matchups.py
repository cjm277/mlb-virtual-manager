"""Batter-vs-pitcher matchup scores.

How a score is built (all from data, no LLM):
  1. Which side the batter hits from against this pitcher (switch hitters bat opposite the pitcher's hand).
  2. How often the pitcher throws fastballs / breaking balls / offspeed to hitters on that side.
  3. For each pitch group, average two numbers: the batter's xwOBA against that group (vs that pitcher hand)
     and the pitcher's xwOBA allowed with that group (to that side).
  4. Weight those averages by the pitcher's usage, giving an expected xwOBA for the matchup.
  5. Compare to league average: higher = edge to the batter, lower = edge to the pitcher.
  6. What to hunt / beware: among pitch groups he throws this hitter at least 12% of the time, the group
     with the best combined number (the hitter's xwOBA vs it and the pitcher's xwOBA allowed with it) is the
     one to sit on; the worst is the one to lay off, if it is clearly worse (by .030 or more).
Missing pieces fall back to the player's overall number vs that hand, then to league average.

Shrink toward season quality (Phase 8+): on every 2026 start, the pitch-type part of this score (the difference
between steps 2-4 and simply averaging the hitter's xwOBA vs this hand with the pitcher's xwOBA allowed to this
side) did not predict how hitters actually did (scripts/lineup_params.py). So the expected xwOBA keeps only
PITCH_TYPE_WEIGHT of that difference (from data/lineup_params.json; 0 on 2026 data). The pitch-group detail and
hunt / beware stay in the output as scouting color for the hitter plans.
"""

from __future__ import annotations

import json
from functools import lru_cache

from backend import config
from backend.engine.common import GROUP_NAMES, league_rates
from backend.engine.hitting import batter_split
from backend.engine.pitching import arsenal, pitcher_split, usage_by_group
from backend.engine.roster import player_info

EDGE = 0.020  # xwOBA points either side of league average before we call it an edge
HUNT_MIN_USAGE = 12.0
BEWARE_GAP = 0.030


@lru_cache(maxsize=1)
def pitch_type_weight() -> float:
    f = config.REPO_ROOT / "data" / "lineup_params.json"
    return float(json.loads(f.read_text(encoding="utf-8")).get("matchup_lambda", 1.0)) if f.exists() else 1.0


def batting_side(bat_side: str | None, pitch_hand: str | None) -> str:
    if bat_side == "S":
        return "L" if pitch_hand == "R" else "R"
    return bat_side or "R"


def _pitcher_group_xwoba(pitcher_id: int, game_date: str, stand: str) -> dict[str, float]:
    """Usage-weighted xwOBA allowed per pitch group to one side."""
    sums: dict[str, list[float]] = {}
    for row in arsenal(pitcher_id, game_date, stand):
        if row["xwoba"] is not None and row["group"] in GROUP_NAMES:
            s = sums.setdefault(row["group"], [0.0, 0.0])
            s[0] += row["xwoba"] * row["pitches"]
            s[1] += row["pitches"]
    return {g: s[0] / s[1] for g, s in sums.items() if s[1]}


def matchup(batter_id: int, pitcher_id: int, game_date: str, weight: float | None = None) -> dict:
    """weight: how much of the pitch-type detail to keep (None = the measured PITCH_TYPE_WEIGHT; 1.0 = raw)."""
    b, p = player_info(batter_id) or {}, player_info(pitcher_id) or {}
    hand = p.get("pitch_hand") or "R"
    side = batting_side(b.get("bat_side"), hand)
    league = league_rates(game_date)["xwoba"]
    usage = usage_by_group(pitcher_id, game_date, side)
    p_group = _pitcher_group_xwoba(pitcher_id, game_date, side)
    b_vs_hand = batter_split(batter_id, game_date, hand)
    p_vs_side = pitcher_split(pitcher_id, game_date, side)

    expected, parts, flags = 0.0, {}, set()
    for g, share in usage.items():
        bs = batter_split(batter_id, game_date, hand, g, ["xwoba"])
        b_x = bs["xwoba"] if bs["xwoba"] is not None else (b_vs_hand["xwoba"] or league)
        p_x = p_group.get(g, p_vs_side["xwoba"] or league)
        if bs["sample"]["flag"] == "small":
            flags.add(f"batter has a small sample vs {GROUP_NAMES[g]}")
        parts[GROUP_NAMES[g]] = {"pitcher_usage_pct": round(share, 1), "batter_xwoba": round(b_x, 3),
                                 "pitcher_xwoba_allowed": round(p_x, 3)}
        expected += share / 100 * (b_x + p_x) / 2
    if not usage:  # no pitch data at all for this pitcher
        expected = ((b_vs_hand["xwoba"] or league) + (p_vs_side["xwoba"] or league)) / 2
        flags.add("no pitch-type data for this pitcher; used overall splits")
    if b_vs_hand["sample"]["flag"] == "small":
        flags.add(f"batter has a small sample vs {'LHP' if hand == 'L' else 'RHP'}")
    if p_vs_side["sample"]["flag"] == "small":
        flags.add(f"pitcher has a small sample vs {'LHB' if side == 'L' else 'RHB'}")

    base = ((b_vs_hand["xwoba"] or league) + (p_vs_side["xwoba"] or league)) / 2
    keep = pitch_type_weight() if weight is None else weight
    expected = base + keep * (expected - base)
    diff = expected - league
    combined = {name: (v["batter_xwoba"] + v["pitcher_xwoba_allowed"]) / 2 for name, v in parts.items()
                if v["pitcher_usage_pct"] >= HUNT_MIN_USAGE}
    hunt = max(combined, key=combined.get) if combined else None
    beware = min(combined, key=combined.get) if combined else None
    if beware == hunt or (hunt and combined[hunt] - combined[beware] < BEWARE_GAP):
        beware = None
    return {
        "batter": b.get("full_name"), "batter_id": batter_id, "bats": side,
        "pitcher": p.get("full_name"), "pitcher_id": pitcher_id, "throws": hand,
        "platoon_advantage": "batter" if side != hand else "pitcher",
        "expected_xwoba": round(expected, 3), "league_xwoba": round(league, 3),
        "edge": "batter" if diff > EDGE else "pitcher" if diff < -EDGE else "even",
        "batter_k_pct_vs_hand": b_vs_hand["k_pct"], "pitcher_k_pct_vs_side": p_vs_side["k_pct"],
        "by_pitch_group": parts,
        "hunt_pitch": hunt, "beware_pitch": beware,
        "flags": sorted(flags),
    }


def matchups(batter_ids: list[int], pitcher_id: int, game_date: str) -> list[dict]:
    """Score several batters against one pitcher, best matchup for the batter first."""
    return sorted((matchup(b, pitcher_id, game_date) for b in batter_ids), key=lambda m: -m["expected_xwoba"])
