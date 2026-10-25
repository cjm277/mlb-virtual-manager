"""Multi-year defensive data for the win model (about 40 small downloads, under a minute).

Adds two tables to data/mlb.sqlite (dropped and rebuilt each run, so it is safe to re-run):
  fielding_by_position  season x player x position: Outs Above Average and fielding runs prevented AT THAT
                        POSITION (Savant, one leaderboard per position), plus innings and starts there (Stats API).
  framing_history       season x catcher: framing runs and pitches received (Savant).
Seasons 2023-2026. A game only ever uses seasons before its own (see backend/engine/defense.py).

Usage: python scripts/fetch_defense.py   (run after scripts/build_dataset.py if the database is rebuilt)
"""

from __future__ import annotations

import io
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_dataset import DB_PATH, DEFAULT_RAW_DIR, SAVANT, STATS_API, fetch_to_cache, read_csv, read_json  # noqa: E402

SEASONS = (2023, 2024, 2025, 2026)
POS_CODES = {"1B": 3, "2B": 4, "3B": 5, "SS": 6, "LF": 7, "CF": 8, "RF": 9}
RAW = DEFAULT_RAW_DIR / "defense"


def innings(text) -> float:
    """Stats API innings '531.1' = 531 and 1/3."""
    if text in (None, ""):
        return 0.0
    whole, _, outs = str(text).partition(".")
    return int(whole) + int(outs or 0) / 3


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    jobs = []
    for s in SEASONS:
        for pos, code in POS_CODES.items():
            jobs.append((f"{SAVANT}/leaderboard/outs_above_average?type=Fielder&startYear={s}&endYear={s}&split=no"
                         f"&team=&range=year&min=1&pos={code}&roles=&viz=hide&csv=true", RAW / f"oaa_{s}_{pos}.csv.gz"))
        jobs.append((f"{SAVANT}/leaderboard/catcher-framing?type=catcher&seasonStart={s}&seasonEnd={s}&team=&min=1&csv=true",
                     RAW / f"framing_{s}.csv.gz"))
        jobs.append((f"{STATS_API}/stats?stats=season&group=fielding&season={s}&sportId=1&playerPool=ALL&limit=10000",
                     RAW / f"fielding_{s}.json.gz"))
    got = sum(fetch_to_cache(u, p) for u, p in jobs)
    print(f"{len(jobs)} files ({got} downloaded, {len(jobs) - got} already cached) in {RAW}")

    oaa_rows, inn_rows, frame_rows = [], [], []
    for s in SEASONS:
        for pos in POS_CODES:
            df = read_csv(RAW / f"oaa_{s}_{pos}.csv.gz")
            for r in df.itertuples():
                oaa_rows.append({"season": s, "player_id": int(r.player_id), "position": pos,
                                 "outs_above_average": r.outs_above_average,
                                 "fielding_runs_prevented": pd.to_numeric(r.fielding_runs_prevented, errors="coerce")})
        for sp in read_json(RAW / f"fielding_{s}.json.gz")["stats"][0]["splits"]:
            pos = sp.get("position", {}).get("abbreviation")
            if pos in POS_CODES or pos == "C":
                inn_rows.append({"season": s, "player_id": sp["player"]["id"], "position": pos,
                                 "innings": innings(sp["stat"].get("innings")), "games_started": sp["stat"].get("gamesStarted") or 0})
        df = read_csv(RAW / f"framing_{s}.csv.gz")
        for r in df.itertuples():
            frame_rows.append({"season": s, "player_id": int(r.id), "pitches": r.pitches, "framing_runs": round(r.rv_tot, 2)})

    oaa = pd.DataFrame(oaa_rows)
    inn = pd.DataFrame(inn_rows).groupby(["season", "player_id", "position"], as_index=False).sum()   # traded players
    merged = inn.merge(oaa, on=["season", "player_id", "position"], how="left")
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS fielding_by_position")
    con.execute("DROP TABLE IF EXISTS framing_history")
    merged.to_sql("fielding_by_position", con, index=False)
    pd.DataFrame(frame_rows).to_sql("framing_history", con, index=False)
    con.execute("CREATE INDEX IF NOT EXISTS ix_fbp ON fielding_by_position(player_id, position, season)")
    con.execute("CREATE INDEX IF NOT EXISTS ix_frh ON framing_history(player_id, season)")
    con.commit()
    print(merged.groupby("season").agg(rows=("player_id", "size"), rated=("fielding_runs_prevented", "count")).to_string())
    print(pd.DataFrame(frame_rows).groupby("season").size().to_string())
    con.execute("VACUUM")
    con.close()


if __name__ == "__main__":
    main()
