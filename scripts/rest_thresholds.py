"""Where the rest-day rule's thresholds come from: how long real 2026 regulars went between days off.

For every regular (100+ starts for one team), count each run of straight team games he started that ended
with a game he didn't start. Runs include rest days, platoon sits and injuries alike.

Usage:
  python scripts/rest_thresholds.py
Writes:
  evidence/tests/phase7_rest_thresholds.md
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import db  # noqa: E402
from backend.engine.workload import REST_AFTER  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "evidence" / "tests" / "phase7_rest_thresholds.md"


def main() -> None:
    games = defaultdict(list)
    for r in db.rows("SELECT DISTINCT team_id, game_pk, game_date FROM batting_lines ORDER BY game_date, game_pk"):
        games[r["team_id"]].append(r["game_pk"])
    starts, pos = defaultdict(set), defaultdict(Counter)
    for r in db.rows("SELECT team_id, game_pk, player_id, start_position FROM batting_lines WHERE is_starter = 1"):
        starts[(r["team_id"], r["player_id"])].add(r["game_pk"])
        pos[r["player_id"]][r["start_position"]] += 1
    runs: dict[str, list[int]] = {"C": [], "other": []}
    players = {"C": 0, "other": 0}
    for (tid, pid), s in starts.items():
        if len(s) < 100:
            continue
        kind = "C" if pos[pid].most_common(1)[0][0] == "C" else "other"
        players[kind] += 1
        run, began = 0, False
        for pk in games[tid]:
            if pk in s:
                run, began = run + 1, True
            elif began and run:
                runs[kind].append(run)
                run = 0
    lines = ["# Rest-day rule: thresholds from 2026 data", "",
             "Runs of straight starts by 2026 regulars (100+ starts for one team) that ended with a game off "
             "(rest day, platoon sit or injury). Built by `scripts/rest_thresholds.py`.", "",
             "| Group | Regulars | Runs | Median | 75th percentile | 90th percentile | Rule: rest suggested at |",
             "|---|---|---|---|---|---|---|"]
    for kind, label in (("C", "Catchers"), ("other", "Everyone else")):
        v = sorted(runs[kind])
        q = lambda p: v[int(p * (len(v) - 1))]  # noqa: E731
        lines.append(f"| {label} | {players[kind]} | {len(v):,} | {q(.5)} | {q(.75)} | {q(.9)} | **{REST_AFTER[kind]} straight starts** |")
    lines += ["", "The rule fires at the 75th percentile: a run longer than three out of four real runs. It **suggests** "
              "rest; the Bench Coach picks the day, preferring one where the player's matchup is weak, so the day off "
              "costs the least. Real managers tend to rest on a schedule, regardless of the opponent.", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
