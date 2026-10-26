"""Score a lineup built by hand against the one the app builds, with the app's own win model (no LLM, free).

Phase 9 uses it to put a number on the human side of the before-and-after: the same game, the same opposing
starter, the same pre-game data. It reports expected runs scored, runs saved on defense and win probability for
both lineups, then each place where the hand-built one differs and what that costs.

Usage:
  python scripts/score_hand_lineup.py --team TOR --date 2026-08-12 ^
      --lineup "Springer LF, Guerrero 1B, Kirk C, Bichette SS, Varsho CF, Gimenez 2B, Clement 3B, Barger RF, Santander DH"
  Optional: --sp "Bello"   (the opposing starter you planned against; default: the app's predicted starter)
            --out evidence/user_test/hand_vs_app.md
The batting order is the order you list. Names can be last names or full names (accents optional).
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import db  # noqa: E402
from backend.engine import defense, roster, rotation, winmodel  # noqa: E402

POS = {"C", "1B", "2B", "3B", "SS", "LF", "CF", "RF", "DH"}


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower().strip()


def find(name: str, pool: list[dict]) -> dict:
    n = norm(name)
    hits = [r for r in pool if norm(r["full_name"]) == n] or \
           [r for r in pool if norm(r["full_name"]).split()[-1] == n] or \
           [r for r in pool if n in norm(r["full_name"])]
    if len(hits) != 1:
        options = ", ".join(r["full_name"] for r in (hits or pool))
        raise SystemExit(f"'{name}' matches {len(hits)} players. Choose from: {options}")
    return hits[0]


def team_id(code: str) -> int:
    r = db.one("SELECT team_id FROM teams WHERE abbrev = ? OR CAST(team_id AS TEXT) = ? OR name LIKE ?",
               code.upper(), code, f"%{code}%")
    if not r:
        raise SystemExit(f"Unknown team {code}")
    return r["team_id"]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--lineup", required=True, help='"Name POS, Name POS, ..." in batting order')
    ap.add_argument("--sp", help="opposing starter's name (default: the app's predicted starter)")
    ap.add_argument("--game-number", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()

    tid, d = team_id(a.team), a.date
    g = db.one("SELECT game_pk, home_team_id h, away_team_id w FROM games WHERE game_date = ? AND game_number = ? "
               "AND (home_team_id = ? OR away_team_id = ?) UNION ALL SELECT game_pk, home_team_id, away_team_id "
               "FROM future_games WHERE game_date = ? AND (home_team_id = ? OR away_team_id = ?) LIMIT 1",
               d, a.game_number, tid, tid, d, tid, tid)
    if not g:
        raise SystemExit(f"No game for {a.team} on {d}")
    home = g["h"] == tid
    opp = g["w"] if home else g["h"]
    pitchers = [r for r in roster.active_roster(opp, d) if roster.is_pitcher(r)]
    if a.sp:
        sp = find(a.sp, pitchers)["player_id"]
        sp_note = "the starter you planned against"
    else:
        sp = rotation.predict_starter(opp, d, a.game_number)["predicted"]["player_id"]
        sp_note = "the app's predicted starter"

    hitters = [r for r in roster.active_roster(tid, d) if not roster.is_pitcher(r)]
    picks = []
    for slot, part in enumerate([p.strip() for p in a.lineup.split(",") if p.strip()], start=1):
        *name, pos = part.split()
        pos = pos.upper()
        if pos not in POS:
            raise SystemExit(f"'{part}': end each entry with a position ({', '.join(sorted(POS))})")
        picks.append((slot, find(" ".join(name), hitters), pos))
    problems = []
    if len(picks) != 9:
        problems.append(f"{len(picks)} players listed, not 9")
    if sorted(p for _, _, p in picks) != sorted(POS):
        problems.append("every position (C, 1B, 2B, 3B, SS, LF, CF, RF, DH) must be filled exactly once")
    if problems:
        raise SystemExit("Not a legal lineup: " + "; ".join(problems))

    lg = winmodel.league()["rpg"]
    hand_runs = winmodel.expected_runs([(s, r["player_id"]) for s, r, _ in picks], d, sp)
    hand_def = sum(defense.runs_saved(r["player_id"], p, d) for _, r, p in picks)
    hand_wp = winmodel.win_prob(hand_runs + hand_def, lg, home)
    model = winmodel.best_lineup(tid, d, sp, home=home)
    app_runs, app_def = model["expected_runs"], model["defense_runs_saved_per_game"]
    app_wp = winmodel.win_prob(app_runs + app_def, lg, home)

    # Where the hand lineup differs, and the habits behind it
    app_ids = {x["player_id"]: x for x in model["lineup"]}
    value = {r["player_id"]: winmodel.pa_runs(r["player_id"], d, sp) for r in hitters}
    notes = []
    for s, r, p in picks:
        pid = r["player_id"]
        elig = winmodel.eligible_positions(pid, d)
        if p not in elig:
            notes.append(f"{r['full_name']} at {p}: he hasn't started there this season (out of position).")
        if pid not in app_ids:
            notes.append(f"{r['full_name']} starts in yours, not the app's ({1000 * value[pid]:+.1f} runs per 1,000 PA "
                         f"vs average against this starter).")
        elif app_ids[pid]["position"] != p:
            notes.append(f"{r['full_name']}: you have him at {p}, the app at {app_ids[pid]['position']}.")
    for x in model["lineup"]:
        if x["player_id"] not in {r["player_id"] for _, r, _ in picks}:
            notes.append(f"{x['name']} sits in yours, starts in the app's ({1000 * x['runs_per_pa_vs_avg']:+.1f} runs per "
                         "1,000 PA vs average against this starter).")
    ranked = sorted((value[r["player_id"]] for _, r, _ in picks), reverse=True)
    out_of_order = sum(1 for (s, r, _), v in zip(picks, ranked) if value[r["player_id"]] != v)
    if out_of_order:
        notes.append(f"Batting order: {out_of_order} of 9 slots don't follow the hitters' expected value against this "
                     "starter (the best hitters bat most often at the top).")
    for r in [r for _, r, p in picks if p == "C"]:
        if any(r["full_name"] in n and "catch today" in n for n in model["rest_decisions"]):
            notes.append(f"Workload: {r['full_name']} has caught {winmodel.CATCHER_MAX_STARTS} of the team's last "
                         f"{winmodel.CATCHER_WINDOW} games, so the app doesn't let him catch today. A one-game score "
                         "doesn't charge for wearing him down, so this choice flatters the hand-built lineup.")
    throws = (roster.player_info(sp) or {}).get("pitch_hand") or "R"
    same_side = [r["full_name"] for _, r, _ in picks if r.get("bat_side") == throws]
    if same_side:
        notes.append(f"{len(same_side)} hitters bat {throws} against a {throws}HP (no platoon edge): {', '.join(same_side)}.")

    wp_gap = 100 * (app_wp - hand_wp)
    name = lambda pid: roster.player_name(pid)  # noqa: E731
    L = [
        f"## Hand-built vs app lineup: {name(sp)} ({throws}HP, {sp_note}), {d}",
        "",
        "Scored with the app's own win model (`backend/engine/winmodel.py`): the same pre-game data for both, the "
        "same opposing starter. Win probability is against a league-average opponent, so only the difference matters.",
        "",
        "| | Expected runs scored | Runs saved on defense | Win probability |",
        "|---|---|---|---|",
        f"| Hand-built | {hand_runs:.2f} | {hand_def:+.2f} | {100 * hand_wp:.1f}% |",
        f"| App | {app_runs:.2f} | {app_def:+.2f} | {100 * app_wp:.1f}% |",
        f"| **Difference (app minus hand)** | **{app_runs - hand_runs:+.2f}** | **{app_def - hand_def:+.2f}** | "
        f"**{wp_gap:+.1f} points** |",
        "",
        f"A gap of {wp_gap:+.1f} win-probability points on one game is about {wp_gap * 1.62:+.1f} wins over 162 games "
        "if every game were set this way. That is one game's illustration, not the measured season value.",
        "",
        "| Slot | Hand-built | App |",
        "|---|---|---|",
        *[f"| {s} | {r['full_name']} ({p}) | {model['lineup'][s - 1]['name']} ({model['lineup'][s - 1]['position']}) |"
          for s, r, p in picks],
        "",
        "**Where they differ:**",
        "",
        *([f"- {n}" for n in notes] if notes else ["- The two lineups are the same."]),
        "",
    ]
    text = "\n".join(L)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
