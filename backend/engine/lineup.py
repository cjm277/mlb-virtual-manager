"""Predict a team's starting lineup from its recent lineups.

Looks at the team's last 10 games before this one, preferring games against a starting pitcher of the
same hand as the one it will face (teams platoon). The 9 active players who started most often make the
lineup; batting order comes from each player's usual lineup slot, and positions from where he usually starts.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from backend import db
from backend.engine.roster import active_roster, is_pitcher, player_info

WINDOW = 10
LOOKBACK = 40
POSITIONS = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"]


def _recent_games(team_id: int, game_date: str, vs_hand: str | None) -> tuple[list[int], str]:
    games = db.rows("""
        SELECT bl.game_pk, MAX(bl.game_date) d,
               (SELECT p.pitch_hand FROM pitching_lines op JOIN players p USING(player_id)
                 WHERE op.game_pk = bl.game_pk AND op.team_id <> ? AND op.is_starter = 1) AS opp_hand
        FROM batting_lines bl WHERE bl.team_id = ? AND bl.game_date < ?
        GROUP BY bl.game_pk ORDER BY d DESC LIMIT ?""", team_id, team_id, game_date, LOOKBACK)
    if vs_hand:
        same = [g["game_pk"] for g in games if g["opp_hand"] == vs_hand][:WINDOW]
        if len(same) >= 5:
            return same, f"last {len(same)} games vs {'LHP' if vs_hand == 'L' else 'RHP'}"
    recent = [g["game_pk"] for g in games[:WINDOW]]
    return recent, f"last {len(recent)} games"


def predict_lineup(team_id: int, game_date: str, vs_hand: str | None = None) -> dict:
    game_pks, basis = _recent_games(team_id, game_date, vs_hand)
    active = {r["player_id"]: r for r in active_roster(team_id, game_date) if not is_pitcher(r)}
    if not game_pks:
        return {"lineup": [], "basis": "no games played yet", "bench": list(active)}
    marks = ",".join("?" * len(game_pks))
    starts = db.rows(f"""SELECT player_id, lineup_slot, start_position FROM batting_lines
                         WHERE team_id = ? AND is_starter = 1 AND game_pk IN ({marks})""", team_id, *game_pks)
    count, slots, spots = Counter(), defaultdict(list), defaultdict(Counter)
    for s in starts:
        if s["player_id"] in active:
            count[s["player_id"]] += 1
            slots[s["player_id"]].append(s["lineup_slot"])
            spots[s["player_id"]][s["start_position"]] += 1

    nine = [pid for pid, _ in count.most_common(9)]
    # Make sure a catcher is in: swap out the least-used non-catcher if needed.
    if nine and not any(spots[p]["C"] for p in nine):
        catchers = sorted((p for p in count if spots[p]["C"] and p not in nine), key=lambda p: -spots[p]["C"])
        if catchers:
            nine[-1] = catchers[0]

    # Positions: most-established players claim their usual spot first.
    assigned: dict[int, str] = {}
    open_spots = set(POSITIONS)
    for pid in sorted(nine, key=lambda p: -count[p]):
        for pos, _ in spots[pid].most_common():
            if pos in open_spots:
                assigned[pid] = pos
                open_spots.discard(pos)
                break
    for pid in nine:
        if pid not in assigned and open_spots:
            assigned[pid] = "DH" if "DH" in open_spots else sorted(open_spots)[0]
            open_spots.discard(assigned[pid])

    order = sorted(nine, key=lambda p: sum(slots[p]) / len(slots[p]))
    lineup = []
    for i, pid in enumerate(order, 1):
        info = player_info(pid) or {}
        lineup.append({"slot": i, "player_id": pid, "name": info.get("full_name"), "position": assigned.get(pid),
                       "bats": info.get("bat_side"), "starts_in_window": count[pid]})
    bench = [{"player_id": pid, "name": r["full_name"], "position": r["position"], "bats": r["bat_side"]}
             for pid, r in active.items() if pid not in nine]
    return {"lineup": lineup, "bench": bench, "basis": basis}
