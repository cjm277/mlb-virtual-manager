# Phase 2 data spot-checks

Run 2026-10-24 08:15 by `scripts/spot_check.py` against `data/mlb.sqlite` (45.0 MB). Published figures come live from the MLB Stats API and Baseball Savant.

**30 of 30 checks passed.**

| Check | Ours | Published / expected | Result |
|---|---|---|---|
| Completed 2026 regular-season games (one cancelled game never made up) | 2429 | 2429 | PASS |
| Teams with 162 games (BAL and NYY 161, from the cancelled game) | 28 at 162; short: BAL, NYY | 28 at 162; short: BAL, NYY | PASS |
| Games with a box score | 2429 | 2429 | PASS |
| Games with Statcast pitch data | 2429 | 2429 | PASS |
| Roster stints rebuild the API's active roster exactly (every team, every game date) | 4,808 of 4,808 | 4,808 of 4,808 | PASS |
| Blue Jays active roster on 2026-06-16 matches the live API (includes starter Dylan Cease) | 25 players, Cease in | 25 players, Cease in | PASS |
| Vladdy through 2026-06-15: G | 68 | 68 | PASS |
| Vladdy through 2026-06-15: PA | 288 | 288 | PASS |
| Vladdy through 2026-06-15: AB | 246 | 246 | PASS |
| Vladdy through 2026-06-15: H | 69 | 69 | PASS |
| Vladdy through 2026-06-15: HR | 3 | 3 | PASS |
| Vladdy through 2026-06-15: BB | 34 | 34 | PASS |
| Vladdy through 2026-06-15: K | 30 | 30 | PASS |
| Vladdy through 2026-06-15: AVG | .280 | .280 | PASS |
| Vladdy through 2026-06-15: OPS | .738 | .738 | PASS |
| Vladdy through 2026-06-15: Statcast AB/H/HR match box scores | 246/69/3 | 246/69/3 | PASS |
| Dylan Cease through 2026-06-15: G | 12 | 12 | PASS |
| Dylan Cease through 2026-06-15: GS | 12 | 12 | PASS |
| Dylan Cease through 2026-06-15: Outs | 204 | 204 | PASS |
| Dylan Cease through 2026-06-15: K | 103 | 103 | PASS |
| Dylan Cease through 2026-06-15: BB | 27 | 27 | PASS |
| Dylan Cease through 2026-06-15: ER | 22 | 22 | PASS |
| Dylan Cease through 2026-06-15: Pitches | 1173 | 1173 | PASS |
| All hitters: full-season AB/H/HR from box scores match official season totals | 100.0% of 750 players | ≥ 99% | PASS |
| Every pitching appearance: Statcast pitch count within 1 of the box score | 100.0% of 20,800 appearances | ≥ 98% | PASS |
| Gausman 2026 4-Seam Fastball: pitches / usage % / whiff % | 1521 / 50.6 / 14.9 | 1521 / 50.6 / 15.0 | PASS |
| Gausman 2026 Split-Finger: pitches / usage % / whiff % | 1177 / 39.2 / 42.9 | 1177 / 39.2 / 42.9 | PASS |
| Gausman 2026 Slider: pitches / usage % / whiff % | 244 / 8.1 / 36.2 | 244 / 8.1 / 36.2 | PASS |
| Vladdy 2025 season from Statcast rollup: PA/H/HR | 680/172/23 | 680/172/23 | PASS |
| data/mlb.sqlite file size | 45.0 MB | < 50 MB (GitHub limit 100 MB) | PASS |

## Notes

- Active roster sizes from the API: median 26 (27 on doubleheader days, 28 from September 1). On 125 of 4,808 team-dates (2.6%) the API lists 24 or fewer, most likely because it caught the roster in the middle of a same-day move (for example, a player placed on the injured list before his replacement was added). We store exactly what the API reports; this is a known limitation for the Team Doctor agent.

## Row counts

| Table | Rows |
|---|---|
| `batting_lines` | 51,706 |
| `catcher_framing` | 113 |
| `future_games` | 2,430 |
| `games` | 2,429 |
| `meta` | 7 |
| `outs_above_average` | 1,131 |
| `pitching_lines` | 20,802 |
| `players` | 1,841 |
| `roster_stints` | 2,858 |
| `season_hitting` | 1,516 |
| `season_pitching` | 1,741 |
| `sprint_speed` | 1,229 |
| `statcast_batter_game` | 170,384 |
| `statcast_batter_season` | 4,447 |
| `statcast_pitcher_game` | 127,292 |
| `statcast_pitcher_season` | 7,940 |
| `teams` | 30 |
| `transactions` | 14,853 |
