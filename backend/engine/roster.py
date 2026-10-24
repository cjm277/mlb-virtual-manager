"""Who can play: the active roster on a date, and who is out (injured list and other lists) and why."""

from __future__ import annotations

import re
from datetime import timedelta

from backend import db
from backend.engine.common import is_future, last_played_day, to_date

LIST_MOVE = re.compile(r"(placed|transferred|activated|reinstated|recalled)\b.*?\b((?:\d+-day )?injured|paternity|bereavement|restricted) list", re.I)
IL_TYPE = re.compile(r"(\d+)-day injured list", re.I)
REASON = re.compile(r"(?:injured|paternity|bereavement|restricted) list[^.]*?(?:retroactive to [A-Za-z]+ \d+, \d{4})?\.\s*(.+)$", re.I)


def player_info(player_id: int) -> dict | None:
    r = db.one("SELECT player_id, full_name, primary_position, bat_side, pitch_hand FROM players WHERE player_id = ?",
               player_id)
    return dict(r) if r else None


def player_name(player_id: int) -> str:
    info = player_info(player_id)
    return info["full_name"] if info else f"player {player_id}"


def roster_date(team_id: int, game_date: str) -> str:
    """The date whose roster applies: the game date itself, or for a 2027 game, the team's last 2026 game."""
    if not is_future(game_date):
        return game_date
    return db.one("SELECT MAX(end_date) d FROM roster_stints WHERE team_id = ?", team_id)["d"]


def _roster_on(team_id: int, on_date: str) -> list[dict]:
    return [dict(r) for r in db.rows("""
        SELECT p.player_id, p.full_name, r.position, p.bat_side, p.pitch_hand
        FROM roster_stints r JOIN players p USING(player_id)
        WHERE r.team_id = ? AND ? BETWEEN r.start_date AND r.end_date
        ORDER BY CASE WHEN r.position IN ('P', 'TWP') THEN 1 ELSE 0 END, r.position, p.full_name""",
        team_id, on_date)]


def active_roster(team_id: int, game_date: str) -> list[dict]:
    """Players who can play on game_date, with position and handedness.

    2026 game: the team's active roster that day.
    2027 game: the team's active roster at the end of 2026, plus players who ended 2026 on the injured list
    (assumed healthy by 2027; each carries a health_note so the staff can confirm).
    """
    players = _roster_on(team_id, roster_date(team_id, game_date))
    if is_future(game_date):
        for p in end_of_season_injured(team_id):
            info = player_info(p["player_id"]) or {}
            players.append({
                "player_id": p["player_id"], "full_name": info.get("full_name"),
                "position": "P" if info.get("primary_position") in ("P", "SP", "RP") else info.get("primary_position"),
                "bat_side": info.get("bat_side"), "pitch_hand": info.get("pitch_hand"),
                "health_note": f"Ended 2026 on the {p['list']} ({p['reason']}). Assumed healthy for 2027; "
                               "confirm with the medical staff.",
            })
    return players


def is_pitcher(roster_row: dict) -> bool:
    return roster_row["position"] in ("P", "TWP")


def _on_lists(team_id: int, as_of: str, exclude: set[int]) -> list[dict]:
    """Players the team had on the injured list (or paternity/bereavement/restricted) going into as_of.

    Read from the team's roster transactions before as_of: the latest list move for each player decides
    whether he is still on a list, and the transaction text gives the reason.
    """
    latest: dict[int, dict] = {}
    for t in db.rows("""SELECT txn_date, txn_id, player_id, description FROM transactions
                        WHERE team_id = ? AND txn_date < ? AND description LIKE '% list%'
                        ORDER BY txn_date, txn_id""", team_id, as_of):
        m = LIST_MOVE.search(t["description"] or "")
        if m:
            latest[t["player_id"]] = {"verb": m.group(1).lower(), "list": m.group(2).lower(), **dict(t)}
    out = []
    for pid, t in latest.items():
        if t["verb"] in ("activated", "reinstated", "recalled") or pid in exclude:
            continue
        il = IL_TYPE.findall(t["description"])
        reason = REASON.search(t["description"])
        info = player_info(pid)
        if not info:  # never appeared in MLB in 2025-26 (minor leaguer on the 40-man): nothing to plan with
            continue
        out.append({
            "player_id": pid, "name": info.get("full_name"), "position": info.get("primary_position"),
            "list": f"{il[-1]}-day injured list" if il else f"{t['list']} list",
            "since": t["txn_date"],
            "reason": reason.group(1).strip() if reason and reason.group(1).strip() else "not stated",
        })
    return sorted(out, key=lambda r: r["since"], reverse=True)


def end_of_season_injured(team_id: int) -> list[dict]:
    """Players who finished 2026 on one of the team's lists (injured, paternity, ...)."""
    after = (to_date(last_played_day()) + timedelta(days=1)).isoformat()
    final_roster = {r["player_id"] for r in _roster_on(team_id, roster_date(team_id, after))}
    return _on_lists(team_id, after, final_roster)


def unavailable_list(team_id: int, game_date: str) -> list[dict]:
    """Players who are out for game_date and why. For a 2027 game nobody is known to be out: players who
    ended 2026 injured are in the active roster with a health_note instead."""
    if is_future(game_date):
        return []
    active_ids = {r["player_id"] for r in active_roster(team_id, game_date)}
    return _on_lists(team_id, game_date, active_ids)
