"""Hitter stats as of a game: blended rates, splits vs left/right pitching, and results vs pitch types."""

from __future__ import annotations

from datetime import timedelta

from backend import db
from backend.engine.common import (GROUP_NAMES, SUM_SELECT, blend_rates, effective_n, is_future, prior_weight,
                                   rates, sample_flag, sum_counts, tidy, to_date)
from backend.engine.roster import player_info

HITTER_KEYS = ["avg", "obp", "slg", "woba", "xwoba", "k_pct", "bb_pct", "hard_hit_pct", "barrel_pct",
               "whiff_pct", "chase_pct"]
VS_PITCH_KEYS = ["xwoba", "whiff_pct", "chase_pct", "hard_hit_pct", "rv_per_100"]


def batter_split(batter_id: int, game_date: str, p_throws: str | None = None,
                 pitch_group: str | None = None, keys: list[str] = HITTER_KEYS) -> dict:
    """Blended (2026 to date + faded 2025) hitting rates, optionally vs one pitcher hand and/or pitch group."""
    where, args = ["batter_id = ?"], [batter_id]
    if p_throws:
        where.append("p_throws = ?"); args.append(p_throws)
    if pitch_group:
        where.append("pitch_group = ?"); args.append(pitch_group)
    cond = " AND ".join(where)
    cur = sum_counts(f"SELECT {SUM_SELECT} FROM statcast_batter_game WHERE {cond} AND game_date < ?", *args, game_date)
    prior = sum_counts(f"SELECT {SUM_SELECT} FROM statcast_batter_season WHERE season = 2025 AND {cond}", *args)
    w = prior_weight(game_date)
    size = "pitches" if pitch_group else "pa"
    blended, w_used = blend_rates(rates(cur) if cur[size] else None, rates(prior) if prior[size] else None, w)
    n = effective_n(cur[size], prior[size], w_used)
    out = tidy({k: blended.get(k) for k in keys})
    out["sample"] = {
        ("pitches_seen" if pitch_group else "pa"): round(n),
        "flag": sample_flag(n, "pitches_seen" if pitch_group else "pa"),
        "pa_2026": cur["pa"], "pa_2025": prior["pa"], "weight_2025": f"{round(w_used * 100)}%",
    }
    return out


def vs_pitch_groups(batter_id: int, game_date: str, p_throws: str | None = None) -> dict:
    return {GROUP_NAMES[g]: batter_split(batter_id, game_date, p_throws, g, VS_PITCH_KEYS) for g in GROUP_NAMES}


def season_line(batter_id: int, game_date: str) -> dict:
    """2026 box-score totals before the game, plus where he has started in the field."""
    r = db.one("""SELECT COUNT(*) g, SUM(is_starter) gs, SUM(pa) pa, SUM(hr) hr, SUM(sb) sb, SUM(cs) cs
                  FROM batting_lines WHERE player_id = ? AND game_date < ?""", batter_id, game_date)
    starts = db.rows("""SELECT start_position, COUNT(*) n FROM batting_lines
                        WHERE player_id = ? AND game_date < ? AND is_starter = 1 GROUP BY 1 ORDER BY n DESC""",
                     batter_id, game_date)
    return {"games": r["g"], "starts": r["gs"] or 0, "pa": r["pa"] or 0, "hr": r["hr"] or 0,
            "sb": r["sb"] or 0, "cs": r["cs"] or 0,
            "starts_by_position": {s["start_position"]: s["n"] for s in starts}}


def recent_form(batter_id: int, game_date: str, days: int = 14) -> dict:
    if is_future(game_date):
        return {"note": "No 2027 games played yet, so there is no recent form."}
    start = (to_date(game_date) - timedelta(days=days)).isoformat()
    c = sum_counts(f"SELECT {SUM_SELECT} FROM statcast_batter_game WHERE batter_id = ? AND game_date >= ? AND game_date < ?",
                   batter_id, start, game_date)
    r = tidy({k: rates(c)[k] for k in ("avg", "obp", "slg", "xwoba", "k_pct")})
    r["pa"] = c["pa"]
    r["flag"] = sample_flag(c["pa"], "pa")
    return r


def speed_and_defense(player_id: int) -> dict:
    """Season-level Statcast skills (published for the full season only)."""
    sprint = db.one("SELECT sprint_speed, competitive_runs FROM sprint_speed WHERE player_id = ? "
                    "ORDER BY season DESC LIMIT 1", player_id)
    oaa = db.rows("SELECT season, position, outs_above_average FROM outs_above_average WHERE player_id = ? "
                  "ORDER BY season DESC", player_id)
    frame = db.one("SELECT framing_runs, strike_rate FROM catcher_framing WHERE player_id = ? "
                   "ORDER BY season DESC LIMIT 1", player_id)
    out = {"sprint_speed_ft_s": sprint["sprint_speed"] if sprint else None}
    if oaa:
        out["outs_above_average"] = {f"{o['position']} {o['season']}": o["outs_above_average"] for o in oaa[:2]}
    if frame:
        out["catcher_framing_runs"] = frame["framing_runs"]
    out["note"] = "Season-level skills (sprint speed 30 ft/s is elite, 27 average; OAA 0 is average)."
    return out


def hitter_profile(batter_id: int, game_date: str) -> dict:
    info = player_info(batter_id) or {}
    return {
        "player_id": batter_id, "name": info.get("full_name"), "bats": info.get("bat_side"),
        "primary_position": info.get("primary_position"),
        "overall": batter_split(batter_id, game_date),
        "vs_LHP": batter_split(batter_id, game_date, "L"),
        "vs_RHP": batter_split(batter_id, game_date, "R"),
        "vs_pitch_types": vs_pitch_groups(batter_id, game_date),
        ("season_2026_full" if is_future(game_date) else "season_2026_so_far"): season_line(batter_id, game_date),
        "last_14_days": recent_form(batter_id, game_date),
        "speed_and_defense": speed_and_defense(batter_id),
    }
