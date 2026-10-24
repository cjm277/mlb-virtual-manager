"""Build the MLB Virtual Manager data snapshot (data/mlb.sqlite).

This is a ONE-TIME build run by the project author. Graders never need to run it:
the finished SQLite file is committed to the repo and the app reads only that file.

Two stages:
  fetch  - download raw data into a cache folder (resumable: files already cached are skipped)
  build  - turn the cached raw data into data/mlb.sqlite

Usage:
  python scripts/build_dataset.py all              # fetch + build
  python scripts/build_dataset.py fetch --test     # tiny smoke run (first 3 game days)
  python scripts/build_dataset.py build

Sources (all free, no key):
  MLB Stats API      statsapi.mlb.com      teams, schedule, players, rosters, transactions, box scores
  Baseball Savant    baseballsavant.mlb.com  Statcast pitch-by-pitch data and season leaderboards
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "data" / "mlb.sqlite"
# Raw downloads (~250 MB) live outside the repo and outside OneDrive so they are never synced or committed.
DEFAULT_RAW_DIR = Path.home() / ".cache" / "mlb-virtual-manager" / "raw"

SEASON = 2026          # the season the app plans games in
PRIOR_SEASON = 2025    # blended in over the first 6 weeks of SEASON
STATS_API = "https://statsapi.mlb.com/api/v1"
SAVANT = "https://baseballsavant.mlb.com"
COMPLETED = {"Final", "Completed Early"}

# ---------------------------------------------------------------------------
# HTTP + cache helpers
# ---------------------------------------------------------------------------

_local = threading.local()


def session() -> requests.Session:
    """One retrying session per thread."""
    if not hasattr(_local, "s"):
        s = requests.Session()
        retry = Retry(total=6, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.headers["User-Agent"] = "mlb-virtual-manager (MGT 409 class project)"
        _local.s = s
    return _local.s


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def fetch_to_cache(url: str, path: Path, timeout: int = 60) -> bool:
    """Download url into a gzip file at path. Returns True if a download happened."""
    if path.exists():
        return False
    resp = session().get(url, timeout=timeout)
    resp.raise_for_status()
    _write_atomic(path, gzip.compress(resp.content))
    return True


def read_json(path: Path):
    return json.loads(gzip.decompress(path.read_bytes()))


def read_csv(path: Path) -> pd.DataFrame:
    raw = gzip.decompress(path.read_bytes()).decode("utf-8-sig")
    if not raw.strip() or raw.lstrip().startswith("<"):
        return pd.DataFrame()
    return pd.read_csv(io.StringIO(raw), low_memory=False)


def run_parallel(jobs: list[tuple[str, Path]], workers: int, label: str, timeout: int = 60) -> None:
    """Fetch many (url, path) pairs in parallel with a simple progress line."""
    todo = [(u, p) for u, p in jobs if not p.exists()]
    print(f"  {label}: {len(jobs) - len(todo)} cached, {len(todo)} to download")
    if not todo:
        return
    done, failed = 0, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_to_cache, u, p, timeout): (u, p) for u, p in todo}
        for fut in as_completed(futures):
            done += 1
            try:
                fut.result()
            except Exception as exc:  # keep going; a rerun retries anything that failed
                failed.append((futures[fut][0], str(exc)[:120]))
            if done % 100 == 0 or done == len(todo):
                print(f"    {label}: {done}/{len(todo)}", flush=True)
    if failed:
        print(f"  !! {len(failed)} {label} downloads failed (rerun to retry). First: {failed[0]}")


# ---------------------------------------------------------------------------
# Stage 1: fetch
# ---------------------------------------------------------------------------


def completed_games(raw: Path, season: int) -> list[dict]:
    """Completed games, once each (a suspended game is listed on both days under one gamePk)."""
    sched = read_json(raw / f"schedule_{season}.json.gz")
    games = {}
    for d in sched["dates"]:
        for g in d["games"]:
            if g["status"]["detailedState"] in COMPLETED:
                games.setdefault(g["gamePk"], g)
    return list(games.values())


def fetch(raw: Path, test: bool) -> None:
    print("Fetching small reference files...")
    small = [
        (f"{STATS_API}/teams?sportId=1&season={SEASON}", raw / f"teams_{SEASON}.json.gz"),
    ]
    for season in (SEASON, PRIOR_SEASON):
        small += [
            (f"{STATS_API}/schedule?sportId=1&season={season}&gameType=R&hydrate=probablePitcher",
             raw / f"schedule_{season}.json.gz"),
            (f"{STATS_API}/sports/1/players?season={season}", raw / f"players_{season}.json.gz"),
        ]
        for group in ("hitting", "pitching"):
            small.append((f"{STATS_API}/stats?stats=season&group={group}&season={season}"
                          f"&sportId=1&playerPool=ALL&limit=5000",
                          raw / f"season_{group}_{season}.json.gz"))
        small += [
            (f"{SAVANT}/leaderboard/sprint_speed?year={season}&position=&team=&min=0&csv=true",
             raw / f"sprint_speed_{season}.csv.gz"),
            (f"{SAVANT}/leaderboard/outs_above_average?type=Fielder&startYear={season}&endYear={season}"
             f"&split=no&team=&range=year&min=1&pos=&roles=&viz=hide&csv=true",
             raw / f"oaa_{season}.csv.gz"),
            (f"{SAVANT}/leaderboard/catcher-framing?type=catcher&seasonStart={season}&seasonEnd={season}"
             f"&team=&min=1&csv=true",
             raw / f"framing_{season}.csv.gz"),
        ]
    # Transactions month by month (injured list moves with reasons, call-ups, options, trades).
    for month in range(2, 11):
        start, end = date(SEASON, month, 1), date(SEASON + (month == 12), month % 12 + 1, 1)
        small.append((f"{STATS_API}/transactions?sportId=1&startDate={start}&endDate={end}",
                      raw / "transactions" / f"{SEASON}_{month:02d}.json.gz"))
    run_parallel(small, workers=4, label="reference", timeout=120)

    games = completed_games(raw, SEASON)
    game_dates = sorted({g["officialDate"] for g in games})
    if test:
        game_dates = game_dates[:3]
        games = [g for g in games if g["officialDate"] in game_dates]

    print(f"Fetching {SEASON} box scores and rosters ({len(games)} games, {len(game_dates)} dates)...")
    box_jobs = [(f"{STATS_API}/game/{g['gamePk']}/boxscore", raw / "boxscore" / f"{g['gamePk']}.json.gz")
                for g in games]
    run_parallel(box_jobs, workers=8, label="box scores")

    team_dates = sorted({(side["team"]["id"], g["officialDate"])
                         for g in games for side in (g["teams"]["home"], g["teams"]["away"])})
    roster_jobs = [(f"{STATS_API}/teams/{t}/roster?rosterType=active&date={d}",
                    raw / "roster" / f"{t}_{d}.json.gz") for t, d in team_dates]
    run_parallel(roster_jobs, workers=8, label="rosters")

    print("Fetching Statcast pitch-by-pitch data (one file per game day)...")
    for season in (SEASON, PRIOR_SEASON):
        dates = sorted({g["officialDate"] for g in completed_games(raw, season)})
        if test:
            dates = dates[:3]
        jobs = [(f"{SAVANT}/statcast_search/csv?all=true&hfGT=R%7C&hfSea={season}%7C&player_type=pitcher"
                 f"&game_date_gt={d}&game_date_lt={d}&type=details",
                 raw / "statcast" / str(season) / f"{d}.csv.gz") for d in dates]
        run_parallel(jobs, workers=3, label=f"statcast {season}", timeout=180)


# ---------------------------------------------------------------------------
# Stage 2: build
# ---------------------------------------------------------------------------

PITCH_GROUP = {
    "FF": "FB", "SI": "FB", "FC": "FB", "FA": "FB",
    "SL": "BRK", "ST": "BRK", "CU": "BRK", "KC": "BRK", "SV": "BRK", "CS": "BRK", "KN": "BRK",
    "CH": "OFF", "FS": "OFF", "FO": "OFF", "SC": "OFF",
}
SWINGS = {"swinging_strike", "swinging_strike_blocked", "foul", "foul_tip", "hit_into_play",
          "foul_bunt", "missed_bunt", "bunt_foul_tip"}
WHIFFS = {"swinging_strike", "swinging_strike_blocked", "foul_tip", "missed_bunt"}
NOT_A_PA = ("caught_stealing", "pickoff", "stolen_base", "wild_pitch", "passed_ball",
            "truncated_pa", "other_advance", "runner_double_play")
NOT_AN_AB = {"walk", "intent_walk", "hit_by_pitch", "sac_fly", "sac_fly_double_play",
             "sac_bunt", "sac_bunt_double_play", "catcher_interf"}
BASES = {"single": 1, "double": 2, "triple": 3, "home_run": 4}

COUNT_COLS = ["pitches", "swings", "whiffs", "called_strikes", "zone_pitches", "chase_swings",
              "bip", "hard_hit", "barrels", "ev_n", "pa", "ab", "h", "tb", "hr", "bb", "k", "hbp",
              "sf", "woba_den"]
SUM_COLS = ["ev_sum", "woba_num", "xwoba_num", "rv_sum"]
PITCH_COLS = ["velo_sum", "velo_n", "spin_sum", "spin_n"]


def statcast_features(df: pd.DataFrame) -> pd.DataFrame:
    """Turn raw pitch rows into one row of countable features per pitch."""
    desc = df["description"].fillna("")
    ev = df["events"].fillna("")
    zone = pd.to_numeric(df["zone"], errors="coerce")
    in_zone = zone.between(1, 9)
    launch = pd.to_numeric(df["launch_speed"], errors="coerce")
    bip = desc.eq("hit_into_play")
    swing = desc.isin(SWINGS)
    # Automatic balls/strikes (intentional walks, pitch-clock violations) are logged as rows
    # but are not thrown pitches; they still count toward the plate-appearance result.
    thrown = ~desc.isin({"automatic_ball", "automatic_strike"})
    pa = ev.ne("") & ~ev.str.startswith(NOT_A_PA)
    woba_den = pd.to_numeric(df["woba_denom"], errors="coerce").fillna(0).eq(1)
    woba_val = pd.to_numeric(df["woba_value"], errors="coerce").fillna(0)
    est = pd.to_numeric(df["estimated_woba_using_speedangle"], errors="coerce")
    # xwOBA: expected value on balls in play, actual value on walks/strikeouts/HBP.
    xwoba = est.where(bip & est.notna(), woba_val)
    velo = pd.to_numeric(df["release_speed"], errors="coerce")
    spin = pd.to_numeric(df["release_spin_rate"], errors="coerce")
    pitch_type = df["pitch_type"].fillna("UN").replace("", "UN")
    out = pd.DataFrame({
        "game_pk": df["game_pk"].astype(int),
        "game_date": df["game_date"],
        "pitcher_id": df["pitcher"].astype(int),
        "batter_id": df["batter"].astype(int),
        "stand": df["stand"],
        "p_throws": df["p_throws"],
        "pitch_type": pitch_type,
        "pitch_group": pitch_type.map(PITCH_GROUP).fillna("OTH"),
        "pitches": thrown.astype(int),
        "swings": swing.astype(int),
        "whiffs": desc.isin(WHIFFS).astype(int),
        "called_strikes": desc.eq("called_strike").astype(int),
        "zone_pitches": (in_zone & thrown).astype(int),
        "chase_swings": (swing & ~in_zone).astype(int),
        "bip": bip.astype(int),
        "hard_hit": (bip & launch.ge(95)).astype(int),
        "barrels": (bip & pd.to_numeric(df["launch_speed_angle"], errors="coerce").eq(6)).astype(int),
        "ev_n": (bip & launch.notna()).astype(int),
        "ev_sum": launch.where(bip & launch.notna(), 0.0),
        "pa": pa.astype(int),
        "ab": (pa & ~ev.isin(NOT_AN_AB)).astype(int),
        "h": ev.isin(BASES).astype(int),
        "tb": ev.map(BASES).fillna(0).astype(int),
        "hr": ev.eq("home_run").astype(int),
        "bb": ev.isin({"walk", "intent_walk"}).astype(int),
        "k": ev.str.startswith("strikeout").astype(int),
        "hbp": ev.eq("hit_by_pitch").astype(int),
        "sf": ev.str.startswith("sac_fly").astype(int),
        "woba_den": woba_den.astype(int),
        "woba_num": woba_val.where(woba_den, 0.0),
        "xwoba_num": xwoba.where(woba_den, 0.0),
        # Run value from the batter's point of view (positive = good for the hitter).
        "rv_sum": pd.to_numeric(df["delta_run_exp"], errors="coerce").fillna(0.0),
        "velo_sum": velo.fillna(0.0),
        "velo_n": velo.notna().astype(int),
        "spin_sum": spin.fillna(0.0),
        "spin_n": spin.notna().astype(int),
    })
    return out


def aggregate(feat: pd.DataFrame, keys: list[str], extra: list[str] | None = None) -> pd.DataFrame:
    cols = COUNT_COLS + SUM_COLS + (extra or [])
    agg = feat.groupby(keys, as_index=False)[cols].sum()
    for c in SUM_COLS + [c for c in (extra or []) if c.endswith("_sum")]:
        agg[c] = agg[c].round(3)
    return agg


def build_statcast(raw: Path, con: sqlite3.Connection) -> None:
    print("Rolling up Statcast...")
    for season in (SEASON, PRIOR_SEASON):
        files = sorted((raw / "statcast" / str(season)).glob("*.csv.gz"))
        pitcher_parts, batter_parts = [], []
        for i, f in enumerate(files, 1):
            df = read_csv(f)
            if df.empty:
                continue
            feat = statcast_features(df)
            if season == SEASON:
                # Per game, so the app can total any date range ("stats as of the day before the game").
                pitcher_parts.append(aggregate(feat, ["game_pk", "game_date", "pitcher_id", "stand", "pitch_type"], PITCH_COLS))
                batter_parts.append(aggregate(feat, ["game_pk", "game_date", "batter_id", "p_throws", "pitch_group"]))
            else:
                pitcher_parts.append(aggregate(feat, ["pitcher_id", "stand", "pitch_type"], PITCH_COLS))
                batter_parts.append(aggregate(feat, ["batter_id", "p_throws", "pitch_group"]))
            if i % 25 == 0:
                print(f"    {season}: {i}/{len(files)} days", flush=True)
        if not pitcher_parts:
            continue
        pitcher = pd.concat(pitcher_parts, ignore_index=True)
        batter = pd.concat(batter_parts, ignore_index=True)
        if season == SEASON:
            pitcher.to_sql("statcast_pitcher_game", con, index=False)
            batter.to_sql("statcast_batter_game", con, index=False)
        else:
            # Re-total day files into one season row per player/split.
            pitcher = pitcher.groupby(["pitcher_id", "stand", "pitch_type"], as_index=False).sum()
            batter = batter.groupby(["batter_id", "p_throws", "pitch_group"], as_index=False).sum()
            pitcher.insert(0, "season", season)
            batter.insert(0, "season", season)
            pitcher.to_sql("statcast_pitcher_season", con, index=False)
            batter.to_sql("statcast_batter_season", con, index=False)
        print(f"  statcast {season}: {len(pitcher):,} pitcher rows, {len(batter):,} batter rows")


def build_reference(raw: Path, con: sqlite3.Connection) -> None:
    teams = read_json(raw / f"teams_{SEASON}.json.gz")["teams"]
    pd.DataFrame([{
        "team_id": t["id"], "name": t["name"], "abbrev": t["abbreviation"], "team_name": t["teamName"],
        "location": t.get("locationName"), "league": t["league"]["name"], "division": t["division"]["name"],
        "venue": t["venue"]["name"],
    } for t in teams]).to_sql("teams", con, index=False)

    people = {}
    for season in (PRIOR_SEASON, SEASON):  # SEASON last so its details win
        for p in read_json(raw / f"players_{season}.json.gz")["people"]:
            people[p["id"]] = {
                "player_id": p["id"], "full_name": p["fullName"],
                "primary_position": p.get("primaryPosition", {}).get("abbreviation"),
                "bat_side": p.get("batSide", {}).get("code"), "pitch_hand": p.get("pitchHand", {}).get("code"),
                "birth_date": p.get("birthDate"), "mlb_debut": p.get("mlbDebutDate"),
                "end_of_season_team_id": p.get("currentTeam", {}).get("id"),
            }
    pd.DataFrame(people.values()).to_sql("players", con, index=False)

    rows = []
    for g in completed_games(raw, SEASON):
        home, away = g["teams"]["home"], g["teams"]["away"]
        rows.append({
            "game_pk": g["gamePk"], "game_date": g["officialDate"], "game_number": g.get("gameNumber", 1),
            "doubleheader": g.get("doubleHeader", "N"), "day_night": g.get("dayNight"),
            "home_team_id": home["team"]["id"], "away_team_id": away["team"]["id"],
            "home_probable_id": home.get("probablePitcher", {}).get("id"),
            "away_probable_id": away.get("probablePitcher", {}).get("id"),
            "home_score": home.get("score"), "away_score": away.get("score"),
            "venue": g.get("venue", {}).get("name"), "status": g["status"]["detailedState"],
        })
    pd.DataFrame(rows).to_sql("games", con, index=False)

    seen, txns = set(), []
    for f in sorted((raw / "transactions").glob("*.json.gz")):
        for t in read_json(f).get("transactions", []):
            if t["id"] in seen or "person" not in t:
                continue
            seen.add(t["id"])
            team = t.get("toTeam") or t.get("fromTeam") or {}
            txns.append({
                "txn_id": t["id"], "txn_date": t.get("date"), "effective_date": t.get("effectiveDate"),
                "team_id": team.get("id"), "player_id": t["person"]["id"], "type_code": t.get("typeCode"),
                "type_desc": t.get("typeDesc"), "description": t.get("description"),
            })
    pd.DataFrame(txns).to_sql("transactions", con, index=False)

    for season in (PRIOR_SEASON, SEASON):
        for group in ("hitting", "pitching"):
            splits = read_json(raw / f"season_{group}_{season}.json.gz")["stats"][0]["splits"]
            rows = []
            for s in splits:
                st = s["stat"]
                row = {"season": season, "player_id": s["player"]["id"], "team_id": s.get("team", {}).get("id")}
                if group == "hitting":
                    row.update(g=st.get("gamesPlayed"), pa=st.get("plateAppearances"), ab=st.get("atBats"),
                               h=st.get("hits"), doubles=st.get("doubles"), triples=st.get("triples"),
                               hr=st.get("homeRuns"), bb=st.get("baseOnBalls"), k=st.get("strikeOuts"),
                               hbp=st.get("hitByPitch"), sf=st.get("sacFlies"), sb=st.get("stolenBases"),
                               cs=st.get("caughtStealing"), avg=st.get("avg"), obp=st.get("obp"),
                               slg=st.get("slg"), ops=st.get("ops"))
                else:
                    row.update(g=st.get("gamesPitched"), gs=st.get("gamesStarted"), outs=st.get("outs"),
                               ip=st.get("inningsPitched"), bf=st.get("battersFaced"), h=st.get("hits"),
                               er=st.get("earnedRuns"), bb=st.get("baseOnBalls"), k=st.get("strikeOuts"),
                               hr=st.get("homeRuns"), sv=st.get("saves"), hld=st.get("holds"),
                               era=st.get("era"), whip=st.get("whip"), pitches=st.get("numberOfPitches"))
                rows.append(row)
            pd.DataFrame(rows).to_sql(f"season_{group}", con, index=False, if_exists="append")

    for season in (PRIOR_SEASON, SEASON):
        sprint = read_csv(raw / f"sprint_speed_{season}.csv.gz")
        if not sprint.empty:
            pd.DataFrame({"season": season, "player_id": sprint["player_id"],
                          "position": sprint["position"], "sprint_speed": sprint["sprint_speed"],
                          "hp_to_1b": pd.to_numeric(sprint["hp_to_1b"], errors="coerce"),
                          "competitive_runs": pd.to_numeric(sprint["competitive_runs"], errors="coerce")}
                         ).to_sql("sprint_speed", con, index=False, if_exists="append")
        oaa = read_csv(raw / f"oaa_{season}.csv.gz")
        if not oaa.empty:
            pd.DataFrame({"season": season, "player_id": oaa["player_id"],
                          "position": oaa["primary_pos_formatted"],
                          "outs_above_average": oaa["outs_above_average"],
                          "fielding_runs_prevented": pd.to_numeric(oaa["fielding_runs_prevented"], errors="coerce")}
                         ).to_sql("outs_above_average", con, index=False, if_exists="append")
        framing = read_csv(raw / f"framing_{season}.csv.gz")
        if not framing.empty:
            pd.DataFrame({"season": season, "player_id": framing["id"], "pitches": framing["pitches"],
                          "framing_runs": framing["rv_tot"].round(2),
                          "strike_rate": (framing["pct_tot"] * 100).round(1)}
                         ).to_sql("catcher_framing", con, index=False, if_exists="append")


def build_games(raw: Path, con: sqlite3.Connection) -> None:
    print("Reading box scores and rosters...")
    games = {g["gamePk"]: g["officialDate"] for g in completed_games(raw, SEASON)}
    bat, pitch = [], []
    for f in sorted((raw / "boxscore").glob("*.json.gz")):
        pk = int(f.name.split(".")[0])
        box = read_json(f)
        for side in ("home", "away"):
            team = box["teams"][side]
            tid = team["team"]["id"]
            starter_id = team["pitchers"][0] if team["pitchers"] else None
            for order, pid in enumerate(team["pitchers"], 1):
                st = team["players"][f"ID{pid}"]["stats"].get("pitching", {})
                pitch.append({
                    "game_pk": pk, "game_date": games.get(pk), "team_id": tid, "player_id": pid,
                    "appearance_order": order, "is_starter": int(pid == starter_id),
                    "outs": st.get("outs", 0), "pitches": st.get("numberOfPitches", st.get("pitchesThrown", 0)),
                    "bf": st.get("battersFaced", 0), "h": st.get("hits", 0), "r": st.get("runs", 0),
                    "er": st.get("earnedRuns", 0), "bb": st.get("baseOnBalls", 0), "k": st.get("strikeOuts", 0),
                    "hr": st.get("homeRuns", 0), "w": st.get("wins", 0), "l": st.get("losses", 0),
                    "sv": st.get("saves", 0), "hld": st.get("holds", 0), "bs": st.get("blownSaves", 0),
                })
            for p in team["players"].values():
                if not p.get("battingOrder"):
                    continue
                st = p["stats"].get("batting", {})
                order = int(p["battingOrder"])
                positions = [pos["abbreviation"] for pos in p.get("allPositions", [])]
                bat.append({
                    "game_pk": pk, "game_date": games.get(pk), "team_id": tid, "player_id": p["person"]["id"],
                    "batting_order": order, "lineup_slot": order // 100, "is_starter": int(order % 100 == 0),
                    "start_position": positions[0] if positions else None, "positions": ",".join(positions),
                    "pa": st.get("plateAppearances", 0), "ab": st.get("atBats", 0), "h": st.get("hits", 0),
                    "doubles": st.get("doubles", 0), "triples": st.get("triples", 0), "hr": st.get("homeRuns", 0),
                    "bb": st.get("baseOnBalls", 0), "ibb": st.get("intentionalWalks", 0),
                    "k": st.get("strikeOuts", 0), "hbp": st.get("hitByPitch", 0), "sf": st.get("sacFlies", 0),
                    "sh": st.get("sacBunts", 0), "r": st.get("runs", 0), "rbi": st.get("rbi", 0),
                    "sb": st.get("stolenBases", 0), "cs": st.get("caughtStealing", 0),
                })
    pd.DataFrame(bat).to_sql("batting_lines", con, index=False)
    pd.DataFrame(pitch).to_sql("pitching_lines", con, index=False)

    # Rosters were pulled for every team on every game date. Store each unbroken stint once
    # (team, player, first and last game date on the active roster) to keep the file small.
    daily = []
    for f in sorted((raw / "roster").glob("*.json.gz")):
        tid, d = f.name.split(".")[0].split("_")
        for r in read_json(f).get("roster", []):
            daily.append((int(tid), d, r["person"]["id"], r.get("position", {}).get("abbreviation")))
    daily_df = pd.DataFrame(daily, columns=["team_id", "roster_date", "player_id", "position"])
    stints = []
    for tid, team_rows in daily_df.groupby("team_id"):
        dates = sorted(team_rows["roster_date"].unique())
        step = {d: i for i, d in enumerate(dates)}
        for pid, rows in team_rows.sort_values("roster_date").groupby("player_id"):
            start = prev = None
            for d, pos in zip(rows["roster_date"], rows["position"]):
                if prev is not None and step[d] != step[prev] + 1:
                    stints.append((tid, pid, pos_last, start, prev))
                    start = None
                start = start or d
                prev, pos_last = d, pos
            stints.append((tid, pid, pos_last, start, prev))
    pd.DataFrame(stints, columns=["team_id", "player_id", "position", "start_date", "end_date"]
                 ).to_sql("roster_stints", con, index=False)


INDEXES = [
    "CREATE INDEX ix_games_date ON games(game_date)",
    "CREATE INDEX ix_games_home ON games(home_team_id, game_date)",
    "CREATE INDEX ix_games_away ON games(away_team_id, game_date)",
    "CREATE INDEX ix_roster ON roster_stints(team_id, start_date, end_date)",
    "CREATE INDEX ix_txn_player ON transactions(player_id, txn_date)",
    "CREATE INDEX ix_bat_player ON batting_lines(player_id, game_date)",
    "CREATE INDEX ix_bat_team ON batting_lines(team_id, game_date)",
    "CREATE INDEX ix_pitch_player ON pitching_lines(player_id, game_date)",
    "CREATE INDEX ix_pitch_team ON pitching_lines(team_id, game_date)",
    "CREATE INDEX ix_pitch_game ON pitching_lines(game_pk, team_id)",
    "CREATE INDEX ix_bat_game ON batting_lines(game_pk, team_id)",
    "CREATE INDEX ix_sc_pitcher ON statcast_pitcher_game(pitcher_id, game_date)",
    "CREATE INDEX ix_sc_batter ON statcast_batter_game(batter_id, game_date)",
]


def build(raw: Path) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    build_reference(raw, con)
    build_games(raw, con)
    build_statcast(raw, con)
    games = pd.read_sql("SELECT MIN(game_date) AS first, MAX(game_date) AS last FROM games", con).iloc[0]
    pd.DataFrame([
        ("built_at_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("season", str(SEASON)), ("prior_season", str(PRIOR_SEASON)),
        ("opening_day", games["first"]), ("last_regular_season_day", games["last"]),
        ("sources", "MLB Stats API (statsapi.mlb.com); Baseball Savant / Statcast (baseballsavant.mlb.com)"),
    ], columns=["key", "value"]).to_sql("meta", con, index=False)
    for sql in INDEXES:
        try:
            con.execute(sql)
        except sqlite3.OperationalError as exc:  # table missing in a partial/test build
            print(f"  (skipped index: {exc})")
    con.commit()
    con.execute("VACUUM")
    con.close()
    tmp.replace(DB_PATH)
    print(f"Wrote {DB_PATH.relative_to(REPO_ROOT)} ({DB_PATH.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stage", choices=["fetch", "build", "all"])
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR, help=f"default: {DEFAULT_RAW_DIR}")
    parser.add_argument("--test", action="store_true", help="fetch only the first 3 game days")
    args = parser.parse_args()
    started = time.time()
    if args.stage in ("fetch", "all"):
        fetch(args.raw_dir, args.test)
    if args.stage in ("build", "all"):
        build(args.raw_dir)
    print(f"Done in {(time.time() - started) / 60:.1f} min")


if __name__ == "__main__":
    sys.exit(main())
