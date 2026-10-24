"""Spot-check data/mlb.sqlite against published numbers and write the evidence report.

Compares our snapshot to live MLB Stats API and Baseball Savant figures, checks that the
two sources agree with each other, and records row counts and file size.

Usage:
  python scripts/spot_check.py
Writes:
  evidence/tests/phase2_spot_checks.md
"""

from __future__ import annotations

import gzip
import io
import json
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "mlb.sqlite"
OUT = REPO_ROOT / "evidence" / "tests" / "phase2_spot_checks.md"
API = "https://statsapi.mlb.com/api/v1"

VLADDY, CEASE, GAUSMAN = 665489, 656302, 592332
THROUGH = "2026-06-15"

con = sqlite3.connect(DB_PATH)
checks: list[tuple[str, str, str, bool]] = []  # (check, ours, published/expected, passed)


def q(sql: str, *args):
    return con.execute(sql, args).fetchone()


def check(name: str, ours, expected, passed: bool | None = None) -> None:
    ok = (str(ours) == str(expected)) if passed is None else passed
    checks.append((name, str(ours), str(expected), ok))


def api(path: str) -> dict:
    return requests.get(f"{API}/{path}", timeout=60).json()


def fmt3(x: float) -> str:
    return f"{x:.3f}".lstrip("0") if x < 1 else f"{x:.3f}"


# --- Coverage --------------------------------------------------------------
# 2,430 scheduled games minus BAL @ NYY on 2026-09-27, which was cancelled and never made up.
check("Completed 2026 regular-season games (one cancelled game never made up)",
      q("SELECT COUNT(DISTINCT game_pk) FROM games")[0], 2429)
per_team = dict(con.execute("""
    SELECT t.abbrev, COUNT(*) FROM (SELECT home_team_id AS team_id FROM games
                                   UNION ALL SELECT away_team_id FROM games) g
    JOIN teams t USING(team_id) GROUP BY t.abbrev""").fetchall())
short = sorted(k for k, n in per_team.items() if n != 162)
check("Teams with 162 games (BAL and NYY 161, from the cancelled game)",
      f"{sum(n == 162 for n in per_team.values())} at 162; short: {', '.join(short)}", "28 at 162; short: BAL, NYY")
check("Games with a box score", q("SELECT COUNT(DISTINCT game_pk) FROM batting_lines")[0], 2429)
check("Games with Statcast pitch data", q("SELECT COUNT(DISTINCT game_pk) FROM statcast_pitcher_game")[0], 2429)

# Roster stints must rebuild the API's own active roster exactly, for every team on every game date.
raw = Path.home() / ".cache" / "mlb-virtual-manager" / "raw" / "roster"
stints = pd.read_sql("SELECT team_id, player_id, start_date, end_date FROM roster_stints", con)
exact, total, sizes = 0, 0, []
for f in raw.glob("*.json.gz"):
    tid, d = f.name.split(".")[0].split("_")
    api_ids = {r["person"]["id"] for r in json.loads(gzip.decompress(f.read_bytes())).get("roster", [])}
    s = stints[(stints.team_id == int(tid)) & (stints.start_date <= d) & (stints.end_date >= d)]
    exact += set(s.player_id) == api_ids
    total += 1
    sizes.append(len(api_ids))
check("Roster stints rebuild the API's active roster exactly (every team, every game date)",
      f"{exact:,} of {total:,}", f"{total:,} of {total:,}", exact == total)
sizes = pd.Series(sizes)
small = int((sizes < 25).sum())
notes = [
    f"Active roster sizes from the API: median {int(sizes.median())} (27 on doubleheader days, 28 from September 1). "
    f"On {small} of {len(sizes):,} team-dates ({small / len(sizes):.1%}) the API lists 24 or fewer, most likely "
    "because it caught the roster in the middle of a same-day move (for example, a player placed on the injured "
    "list before his replacement was added). We store exactly what the API reports; this is a known limitation "
    "for the Team Doctor agent.",
]

jays = {r[0] for r in con.execute("""SELECT player_id FROM roster_stints
                                    WHERE team_id = 141 AND '2026-06-16' BETWEEN start_date AND end_date""")}
live = {r["person"]["id"] for r in api("teams/141/roster?rosterType=active&date=2026-06-16")["roster"]}
check("Blue Jays active roster on 2026-06-16 matches the live API (includes starter Dylan Cease)",
      f"{len(jays)} players, Cease {'in' if CEASE in jays else 'MISSING'}",
      f"{len(live)} players, Cease {'in' if CEASE in live else 'MISSING'}", jays == live and CEASE in jays)

# --- Vladimir Guerrero Jr. through June 15 vs the official Stats API -------------
pub = api(f"people/{VLADDY}/stats?stats=byDateRange&group=hitting&startDate=2026-03-01"
          f"&endDate={THROUGH}&sportId=1")["stats"][0]["splits"][0]["stat"]
ours = pd.read_sql("""SELECT COUNT(*) g, SUM(pa) pa, SUM(ab) ab, SUM(h) h, SUM(doubles) d, SUM(triples) t,
                             SUM(hr) hr, SUM(bb) bb, SUM(k) k, SUM(hbp) hbp, SUM(sf) sf
                      FROM batting_lines WHERE player_id = ? AND game_date <= ?""", con,
                   params=(VLADDY, THROUGH)).iloc[0]
avg = ours.h / ours.ab
obp = (ours.h + ours.bb + ours.hbp) / (ours.ab + ours.bb + ours.hbp + ours.sf)
slg = (ours.h + ours.d + 2 * ours.t + 3 * ours.hr) / ours.ab
for label, mine, theirs in [
    ("G", ours.g, pub["gamesPlayed"]), ("PA", ours.pa, pub["plateAppearances"]), ("AB", ours.ab, pub["atBats"]),
    ("H", ours.h, pub["hits"]), ("HR", ours.hr, pub["homeRuns"]), ("BB", ours.bb, pub["baseOnBalls"]),
    # MLB rounds OBP and SLG to three places before adding them into OPS.
    ("K", ours.k, pub["strikeOuts"]), ("AVG", fmt3(avg), pub["avg"]),
    ("OPS", fmt3(round(obp, 3) + round(slg, 3)), pub["ops"]),
]:
    check(f"Vladdy through {THROUGH}: {label}", int(mine) if not isinstance(mine, str) else mine, theirs)

# Statcast (a different source) should tell the same story for Vladdy.
sc = q("SELECT SUM(ab), SUM(h), SUM(hr) FROM statcast_batter_game WHERE batter_id = ? AND game_date <= ?",
       VLADDY, THROUGH)
check(f"Vladdy through {THROUGH}: Statcast AB/H/HR match box scores",
      f"{sc[0]}/{sc[1]}/{sc[2]}", f"{int(ours.ab)}/{int(ours.h)}/{int(ours.hr)}")

# --- Dylan Cease through June 15 ------------------------------------------------
pub = api(f"people/{CEASE}/stats?stats=byDateRange&group=pitching&startDate=2026-03-01"
          f"&endDate={THROUGH}&sportId=1")["stats"][0]["splits"][0]["stat"]
ours = q("""SELECT COUNT(*), SUM(is_starter), SUM(outs), SUM(k), SUM(bb), SUM(er), SUM(pitches)
            FROM pitching_lines WHERE player_id = ? AND game_date <= ?""", CEASE, THROUGH)
for label, mine, theirs in [
    ("G", ours[0], pub["gamesPlayed"]), ("GS", ours[1], pub["gamesStarted"]), ("Outs", ours[2], pub["outs"]),
    ("K", ours[3], pub["strikeOuts"]), ("BB", ours[4], pub["baseOnBalls"]), ("ER", ours[5], pub["earnedRuns"]),
    ("Pitches", ours[6], pub["numberOfPitches"]),
]:
    check(f"Dylan Cease through {THROUGH}: {label}", mine, theirs)

# --- Whole league: every hitter's full-season box-score totals vs official season totals ----
season = pd.read_sql("SELECT player_id, team_id, ab, h, hr FROM season_hitting WHERE season = 2026", con)
# Traded players: use the combined row (no team) when the API gives one, otherwise sum team rows.
combined = season[season.team_id.isna()].set_index("player_id")
per_team = season[season.team_id.notna()].groupby("player_id")[["ab", "h", "hr"]].sum()
official = per_team.copy()
official.update(combined[["ab", "h", "hr"]])
box = pd.read_sql("SELECT player_id, SUM(ab) ab, SUM(h) h, SUM(hr) hr FROM batting_lines GROUP BY player_id",
                  con).set_index("player_id")
joined = official.join(box.add_suffix("_box"), how="inner")
match = ((joined.ab == joined.ab_box) & (joined.h == joined.h_box) & (joined.hr == joined.hr_box)).mean()
check("All hitters: full-season AB/H/HR from box scores match official season totals",
      f"{match:.1%} of {len(joined):,} players", "≥ 99%", match >= 0.99)

# --- Statcast pitch counts vs box-score pitch counts, every pitcher in every game ----
pc = pd.read_sql("""SELECT b.pitches AS box, s.n AS statcast FROM pitching_lines b
                    JOIN (SELECT game_pk, pitcher_id, SUM(pitches) n FROM statcast_pitcher_game
                          GROUP BY game_pk, pitcher_id) s
                      ON s.game_pk = b.game_pk AND s.pitcher_id = b.player_id""", con)
close = ((pc.box - pc.statcast).abs() <= 1).mean()
check("Every pitching appearance: Statcast pitch count within 1 of the box score",
      f"{close:.1%} of {len(pc):,} appearances", "≥ 98%", close >= 0.98)

# --- Kevin Gausman's 2026 arsenal vs Baseball Savant's own leaderboard ----------
lb = pd.read_csv(io.StringIO(requests.get(
    "https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?type=pitcher&pitchType=&year=2026"
    "&team=&min=1&csv=true", timeout=60).content.decode("utf-8-sig")))
lb = lb[lb.player_id == GAUSMAN].set_index("pitch_type")
mine = pd.read_sql("""SELECT pitch_type, SUM(pitches) n, SUM(swings) sw, SUM(whiffs) wh FROM statcast_pitcher_game
                      WHERE pitcher_id = ? GROUP BY pitch_type""", con, params=(GAUSMAN,)).set_index("pitch_type")
total = mine.n.sum()
for pt in ["FF", "FS", "SL"]:
    if pt in lb.index and pt in mine.index:
        usage, whiff = 100 * mine.n[pt] / total, 100 * mine.wh[pt] / mine.sw[pt]
        check(f"Gausman 2026 {lb.pitch_name[pt]}: pitches / usage % / whiff %",
              f"{mine.n[pt]} / {usage:.1f} / {whiff:.1f}",
              f"{lb.pitches[pt]} / {lb.pitch_usage[pt]} / {lb.whiff_percent[pt]}",
              abs(usage - lb.pitch_usage[pt]) <= 0.5 and abs(whiff - lb.whiff_percent[pt]) <= 1.0)

# --- 2025 season rollup (used for the early-season fade) --------------------------
pub = api(f"people/{VLADDY}/stats?stats=season&group=hitting&season=2025&sportId=1")["stats"][0]["splits"][0]["stat"]
sc = q("SELECT SUM(pa), SUM(h), SUM(hr) FROM statcast_batter_season WHERE season = 2025 AND batter_id = ?", VLADDY)
check("Vladdy 2025 season from Statcast rollup: PA/H/HR", f"{sc[0]}/{sc[1]}/{sc[2]}",
      f"{pub['plateAppearances']}/{pub['hits']}/{pub['homeRuns']}")

# --- File size --------------------------------------------------------------------
size_mb = DB_PATH.stat().st_size / 1e6
check("data/mlb.sqlite file size", f"{size_mb:.1f} MB", "< 50 MB (GitHub limit 100 MB)", size_mb < 50)

# --- Report -----------------------------------------------------------------------
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
counts = [(t, q(f"SELECT COUNT(*) FROM {t}")[0]) for t in tables]
passed = sum(c[3] for c in checks)
lines = [
    "# Phase 2 data spot-checks",
    "",
    f"Run {datetime.now():%Y-%m-%d %H:%M} by `scripts/spot_check.py` against `data/mlb.sqlite` "
    f"({size_mb:.1f} MB). Published figures come live from the MLB Stats API and Baseball Savant.",
    "",
    f"**{passed} of {len(checks)} checks passed.**",
    "",
    "| Check | Ours | Published / expected | Result |",
    "|---|---|---|---|",
    *[f"| {n} | {o} | {e} | {'PASS' if ok else 'FAIL'} |" for n, o, e, ok in checks],
    "",
    "## Notes",
    "",
    *[f"- {n}" for n in notes],
    "",
    "## Row counts",
    "",
    "| Table | Rows |",
    "|---|---|",
    *[f"| `{t}` | {n:,} |" for t, n in counts],
    "",
]
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(lines))
