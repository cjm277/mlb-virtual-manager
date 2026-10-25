"""One more back season for the Marcel projection: Savant expected stats for 2024 (two small downloads, seconds).

Adds the table expected_stats_history to data/mlb.sqlite (dropped and rebuilt each run, so it is safe to re-run):
  season x player x role (batter / pitcher): plate appearances (batters faced), wOBA and xwOBA for that season.
Only full seasons before 2025 are stored; 2025 and 2026 come from the Statcast tables already in the snapshot.
A 2026 game uses 2024 the same way it uses 2025: a finished season, so there is no look-ahead.

Usage: python scripts/fetch_history.py   (run after scripts/build_dataset.py if the database is rebuilt)
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_dataset import DB_PATH, DEFAULT_RAW_DIR, SAVANT, fetch_to_cache, read_csv  # noqa: E402

SEASONS = (2024,)
RAW = DEFAULT_RAW_DIR / "history"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = []
    for s in SEASONS:
        for role in ("batter", "pitcher"):
            path = RAW / f"expected_{role}_{s}.csv.gz"
            fetch_to_cache(f"{SAVANT}/leaderboard/expected_statistics?type={role}&year={s}&position=&team="
                           f"&filterType=bip&min=1&csv=true", path)
            df = read_csv(path)
            for r in df.itertuples():
                pa = pd.to_numeric(r.pa, errors="coerce")
                if pd.isna(pa) or pa <= 0:
                    continue
                rows.append({"season": s, "player_id": int(r.player_id), "role": role, "pa": int(pa),
                             "woba": pd.to_numeric(r.woba, errors="coerce"),
                             "xwoba": pd.to_numeric(r.est_woba, errors="coerce")})
    df = pd.DataFrame(rows)
    con = sqlite3.connect(DB_PATH)
    con.execute("DROP TABLE IF EXISTS expected_stats_history")
    df.to_sql("expected_stats_history", con, index=False)
    con.execute("CREATE INDEX idx_esh ON expected_stats_history (player_id, role, season)")
    con.commit()
    con.close()
    print(df.groupby(["season", "role"]).size().to_string())


if __name__ == "__main__":
    main()
