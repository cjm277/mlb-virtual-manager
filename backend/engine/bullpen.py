"""Bullpen workload and availability going into a game.

Availability rules (written down so a coach can check them):
  Relievers
    unavailable  pitched 3 days in a row, OR threw 30+ pitches yesterday,
                 OR pitched both of the last 2 days with 35+ pitches combined
    limited      pitched yesterday, OR threw 50+ pitches over the last 3 days
    available    otherwise
  Starters (most of this season's appearances were starts)
    listed separately with days of rest; 4+ days of rest = ready to start
"""

from __future__ import annotations

from datetime import timedelta

from backend import db
from backend.engine.common import is_future, to_date
from backend.engine.roster import active_roster, is_pitcher

MIN_START_REST = 4


def _appearances(player_id: int, start: str, end: str) -> dict[str, int]:
    """Pitches thrown per date in [start, end)."""
    return {r["game_date"]: r["p"] for r in db.rows(
        "SELECT game_date, SUM(pitches) p FROM pitching_lines WHERE player_id = ? AND game_date >= ? AND game_date < ? "
        "GROUP BY game_date", player_id, start, end)}


def _role(player_id: int, game_date: str) -> dict:
    r = db.one("""SELECT COUNT(*) g, SUM(is_starter) gs, SUM(sv) sv, SUM(hld) hld FROM pitching_lines
                  WHERE player_id = ? AND game_date < ?""", player_id, game_date)
    g, gs = r["g"] or 0, r["gs"] or 0
    if g < 3:  # too few 2026 games: lean on 2025
        p = db.one("SELECT SUM(g) g, SUM(gs) gs FROM season_pitching WHERE season = 2025 AND player_id = ? "
                   "AND team_id IS NOT NULL", player_id)
        if p and p["g"]:
            g, gs = g + p["g"], gs + (p["gs"] or 0)
    return {"role": "SP" if g and gs / g >= 0.5 else "RP", "games": r["g"] or 0, "saves": r["sv"] or 0,
            "holds": r["hld"] or 0}


def pitcher_workload(player_id: int, game_date: str) -> dict:
    day = to_date(game_date)
    d = lambda n: (day - timedelta(days=n)).isoformat()  # noqa: E731
    week = _appearances(player_id, d(7), game_date)
    yesterday = week.get(d(1), 0)
    streak = 0
    while d(streak + 1) in week:
        streak += 1
    last3 = sum(p for dt, p in week.items() if dt >= d(3))
    last = db.one("SELECT MAX(game_date) d FROM pitching_lines WHERE player_id = ? AND game_date < ?",
                  player_id, game_date)["d"]
    rest = (day - to_date(last)).days - 1 if last else None
    return {"pitches_yesterday": yesterday, "consecutive_days": streak, "pitches_last_3_days": last3,
            "pitches_last_7_days": sum(week.values()), "appearances_last_7_days": len(week),
            "last_appearance": last, "days_rest": rest}


def reliever_status(w: dict) -> tuple[str, str]:
    if w["consecutive_days"] >= 3:
        return "unavailable", "pitched 3 days in a row"
    if w["pitches_yesterday"] >= 30:
        return "unavailable", f"threw {w['pitches_yesterday']} pitches yesterday"
    if w["consecutive_days"] >= 2 and w["pitches_last_3_days"] >= 35:
        return "unavailable", f"back-to-back days, {w['pitches_last_3_days']} pitches"
    if w["pitches_yesterday"] > 0:
        return "limited", f"pitched yesterday ({w['pitches_yesterday']} pitches)"
    if w["pitches_last_3_days"] >= 50:
        return "limited", f"{w['pitches_last_3_days']} pitches over the last 3 days"
    return "available", "rested"


def bullpen_status(team_id: int, game_date: str) -> dict:
    relievers, starters = [], []
    for r in active_roster(team_id, game_date):
        if not is_pitcher(r):
            continue
        role = _role(r["player_id"], game_date)
        w = pitcher_workload(r["player_id"], game_date)
        base = {"player_id": r["player_id"], "name": r["full_name"], "throws": r["pitch_hand"]}
        if role["role"] == "SP":
            ready = w["days_rest"] is None or w["days_rest"] >= MIN_START_REST
            starters.append({**base, "days_rest": w["days_rest"], "last_appearance": w["last_appearance"],
                             "ready_to_start": ready})
        else:
            status, why = reliever_status(w)
            relievers.append({**base, "status": status, "why": why, "saves": role["saves"], "holds": role["holds"],
                              "appearances": role["games"], **{k: w[k] for k in
                              ("pitches_yesterday", "consecutive_days", "pitches_last_3_days", "appearances_last_7_days")}})
    order = {"available": 0, "limited": 1, "unavailable": 2}
    relievers.sort(key=lambda r: (order[r["status"]], -(r["saves"] + r["holds"])))
    if is_future(game_date):
        for s in starters:
            s["ready_to_start"], s["days_rest"] = True, None   # offseason: rest is not a factor
        note = "2027 game: every pitcher is treated as fully rested (no 2027 games played yet)."
    else:
        note = "Workload from games before this one."
    return {"relievers": relievers, "starters": starters, "note": note,
            "rules": "RP unavailable: 3 straight days, 30+ pitches yesterday, or back-to-back with 35+; "
                     "limited: pitched yesterday or 50+ pitches in 3 days. SP ready with 4+ days rest."}
