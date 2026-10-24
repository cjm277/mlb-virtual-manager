"""Who can play: the active roster on a date, and who is out (injured list and other lists) and why."""

from __future__ import annotations

import re

from backend import db

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


def active_roster(team_id: int, game_date: str) -> list[dict]:
    """Players on the team's active roster on game_date, with position and handedness."""
    return [dict(r) for r in db.rows("""
        SELECT p.player_id, p.full_name, r.position, p.bat_side, p.pitch_hand
        FROM roster_stints r JOIN players p USING(player_id)
        WHERE r.team_id = ? AND ? BETWEEN r.start_date AND r.end_date
        ORDER BY CASE WHEN r.position IN ('P', 'TWP') THEN 1 ELSE 0 END, r.position, p.full_name""",
        team_id, game_date)]


def is_pitcher(roster_row: dict) -> bool:
    return roster_row["position"] in ("P", "TWP")


def unavailable_list(team_id: int, game_date: str) -> list[dict]:
    """Players the team has on the injured list (or paternity/bereavement/restricted) going into game_date.

    Read from the team's roster transactions before the game: the latest list move for each player
    decides whether he is still on a list, and the transaction text gives the reason.
    """
    latest: dict[int, dict] = {}
    for t in db.rows("""SELECT txn_date, txn_id, player_id, description FROM transactions
                        WHERE team_id = ? AND txn_date < ? AND description LIKE '% list%'
                        ORDER BY txn_date, txn_id""", team_id, game_date):
        m = LIST_MOVE.search(t["description"] or "")
        if m:
            latest[t["player_id"]] = {"verb": m.group(1).lower(), "list": m.group(2).lower(), **dict(t)}
    active_ids = {r["player_id"] for r in active_roster(team_id, game_date)}
    out = []
    for pid, t in latest.items():
        if t["verb"] in ("activated", "reinstated", "recalled") or pid in active_ids:
            continue
        il = IL_TYPE.findall(t["description"])
        reason = REASON.search(t["description"])
        info = player_info(pid) or {}
        out.append({
            "player_id": pid, "name": info.get("full_name"), "position": info.get("primary_position"),
            "list": f"{il[-1]}-day injured list" if il else f"{t['list']} list",
            "since": t["txn_date"],
            "reason": reason.group(1).strip() if reason and reason.group(1).strip() else "not stated",
        })
    return sorted(out, key=lambda r: r["since"], reverse=True)
