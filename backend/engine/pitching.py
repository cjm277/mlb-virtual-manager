"""Pitcher stats as of a game: results allowed, splits vs left/right hitters, and the pitch arsenal."""

from __future__ import annotations

from backend import db
from backend.engine.common import (COUNTS, PITCH_GROUP, SUM_SELECT, blend_rates, effective_n, prior_weight, rates,
                                   sample_flag, sum_counts, tidy)
from backend.engine.roster import player_info

ALLOWED_KEYS = ["avg", "obp", "slg", "woba", "xwoba", "k_pct", "bb_pct", "whiff_pct", "chase_pct", "csw_pct",
                "hard_hit_pct", "barrel_pct"]
PITCH_KEYS = ["velo", "spin", "whiff_pct", "csw_pct", "xwoba", "rv_per_100"]
EXTRA = ["velo_sum", "velo_n", "spin_sum", "spin_n"]
PITCH_NAMES = {"FF": "4-seam fastball", "SI": "sinker", "FC": "cutter", "SL": "slider", "ST": "sweeper",
               "CU": "curveball", "KC": "knuckle curve", "SV": "slurve", "CH": "changeup", "FS": "splitter",
               "FO": "forkball", "SC": "screwball", "KN": "knuckleball", "EP": "eephus", "CS": "slow curve",
               "FA": "fastball"}


def _pitcher_rates(c: dict) -> dict:
    r = rates(c)
    # Flip run value to the pitcher's point of view (positive = good for the pitcher).
    r["rv_per_100"] = -r["rv_per_100"] if r["rv_per_100"] is not None else None
    r["velo"] = c["velo_sum"] / c["velo_n"] if c.get("velo_n") else None
    r["spin"] = c["spin_sum"] / c["spin_n"] if c.get("spin_n") else None
    return r


def _counts_by(pitcher_id: int, game_date: str, stand: str | None, by_type: bool) -> tuple[dict, dict]:
    """Summed counts for 2026-to-date and 2025, keyed by pitch type (or 'ALL')."""
    cols = ", ".join(f"SUM({c}) AS {c}" for c in COUNTS + EXTRA)
    group = "pitch_type" if by_type else "'ALL'"
    where, args = "pitcher_id = ?", [pitcher_id]
    if stand:
        where += " AND stand = ?"; args.append(stand)
    cur = {r["grp"]: dict(r) for r in db.rows(
        f"SELECT {group} AS grp, {cols} FROM statcast_pitcher_game WHERE {where} AND game_date < ? GROUP BY 1",
        *args, game_date)}
    prior = {r["grp"]: dict(r) for r in db.rows(
        f"SELECT {group} AS grp, {cols} FROM statcast_pitcher_season WHERE season = 2025 AND {where} GROUP BY 1", *args)}
    return cur, prior


def pitcher_split(pitcher_id: int, game_date: str, stand: str | None = None) -> dict:
    """Blended results allowed, optionally vs left-handed (L) or right-handed (R) hitters."""
    cur, prior = _counts_by(pitcher_id, game_date, stand, by_type=False)
    c, p = cur.get("ALL"), prior.get("ALL")
    w = prior_weight(game_date)
    blended, w_used = blend_rates(_pitcher_rates(c) if c and c["pa"] else None,
                                  _pitcher_rates(p) if p and p["pa"] else None, w)
    n = effective_n(c["pa"] if c else 0, p["pa"] if p else 0, w_used)
    out = tidy({k: blended.get(k) for k in ALLOWED_KEYS}) if blended else {k: None for k in ALLOWED_KEYS}
    out["sample"] = {"batters_faced": round(n), "flag": sample_flag(n, "pa"),
                     "bf_2026": c["pa"] if c else 0, "bf_2025": p["pa"] if p else 0,
                     "weight_2025": f"{round(w_used * 100)}%"}
    return out


def arsenal(pitcher_id: int, game_date: str, stand: str | None = None) -> list[dict]:
    """Each pitch he throws: blended usage %, velocity, spin, whiff %, CSW %, xwOBA allowed, run value per 100."""
    cur, prior = _counts_by(pitcher_id, game_date, stand, by_type=True)
    w = prior_weight(game_date)
    tot_c = sum(r["pitches"] for r in cur.values())
    tot_p = sum(r["pitches"] for r in prior.values())
    out = []
    for pt in set(cur) | set(prior):
        if pt in ("UN", "PO"):
            continue
        c, p = cur.get(pt), prior.get(pt)
        use_c = {"usage": 100 * c["pitches"] / tot_c} if c and tot_c else None
        use_p = {"usage": 100 * p["pitches"] / tot_p} if p and tot_p else None
        # Usage blends only when both seasons have pitches at all; a pitch dropped in 2026 fades out with 2025.
        usage, _ = blend_rates(use_c or ({"usage": 0.0} if tot_c else None),
                               use_p or ({"usage": 0.0} if tot_p else None), w)
        blended, w_used = blend_rates(_pitcher_rates(c) if c and c["pitches"] else None,
                                      _pitcher_rates(p) if p and p["pitches"] else None, w)
        n = effective_n(c["pitches"] if c else 0, p["pitches"] if p else 0, w_used)
        if usage["usage"] is None or usage["usage"] < 1:
            continue
        row = {"pitch": PITCH_NAMES.get(pt, pt), "code": pt, "group": PITCH_GROUP.get(pt, "OTH"),
               "usage_pct": round(usage["usage"], 1)}
        row.update(tidy({k: blended.get(k) for k in PITCH_KEYS}))
        row["spin"] = round(row["spin"]) if row.get("spin") else None
        row["pitches"] = round(n)
        row["flag"] = sample_flag(n, "pitch_type")
        out.append(row)
    return sorted(out, key=lambda r: -r["usage_pct"])


def usage_by_group(pitcher_id: int, game_date: str, stand: str) -> dict[str, float]:
    """Share of fastballs / breaking / offspeed he throws to hitters on one side (sums to ~100)."""
    groups: dict[str, float] = {}
    for row in arsenal(pitcher_id, game_date, stand):
        groups[row["group"]] = groups.get(row["group"], 0) + row["usage_pct"]
    total = sum(groups.values()) or 1
    return {g: 100 * v / total for g, v in groups.items() if g in ("FB", "BRK", "OFF")}


def season_line(pitcher_id: int, game_date: str) -> dict:
    """2026 box-score line before the game."""
    r = db.one("""SELECT COUNT(*) g, SUM(is_starter) gs, SUM(outs) outs, SUM(er) er, SUM(k) k, SUM(bb) bb,
                         SUM(bf) bf, SUM(hr) hr, SUM(sv) sv, SUM(hld) hld,
                         AVG(CASE WHEN is_starter = 1 THEN pitches END) AS pitches_per_start,
                         AVG(CASE WHEN is_starter = 1 THEN outs END) AS outs_per_start
                  FROM pitching_lines WHERE player_id = ? AND game_date < ?""", pitcher_id, game_date)
    outs = r["outs"] or 0
    return {
        "games": r["g"], "starts": r["gs"] or 0, "ip": f"{outs // 3}.{outs % 3}",
        "era": round(27 * (r["er"] or 0) / outs, 2) if outs else None,
        "k": r["k"] or 0, "bb": r["bb"] or 0, "hr": r["hr"] or 0, "saves": r["sv"] or 0, "holds": r["hld"] or 0,
        "avg_pitches_per_start": round(r["pitches_per_start"]) if r["pitches_per_start"] else None,
        "avg_innings_per_start": round(r["outs_per_start"] / 3, 1) if r["outs_per_start"] else None,
    }


def prior_season_line(pitcher_id: int) -> dict | None:
    r = db.one("SELECT g, gs, ip, era, k, bb, sv, hld FROM season_pitching WHERE season = 2025 AND player_id = ? "
               "ORDER BY team_id IS NOT NULL LIMIT 1", pitcher_id)
    return dict(r) if r else None


def pitcher_profile(pitcher_id: int, game_date: str) -> dict:
    info = player_info(pitcher_id) or {}
    profile = {
        "player_id": pitcher_id, "name": info.get("full_name"), "throws": info.get("pitch_hand"),
        "season_2026_so_far": season_line(pitcher_id, game_date),
        "overall": pitcher_split(pitcher_id, game_date),
        "vs_LHB": pitcher_split(pitcher_id, game_date, "L"),
        "vs_RHB": pitcher_split(pitcher_id, game_date, "R"),
        "arsenal": arsenal(pitcher_id, game_date),
        "usage_vs_LHB": {k: round(v, 1) for k, v in usage_by_group(pitcher_id, game_date, "L").items()},
        "usage_vs_RHB": {k: round(v, 1) for k, v in usage_by_group(pitcher_id, game_date, "R").items()},
    }
    if prior_weight(game_date) > 0:
        profile["season_2025"] = prior_season_line(pitcher_id)
    return profile
