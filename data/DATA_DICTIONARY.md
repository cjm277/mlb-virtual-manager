# Data dictionary: `data/mlb.sqlite`

One SQLite file holds everything the app reads. It is built once by `scripts/build_dataset.py` from free public sources and committed to the repo. **The app never downloads data**, so graders don't need internet access to run it (only the LLM calls go out).

**Sources:** MLB Stats API (`statsapi.mlb.com`) and Baseball Savant / Statcast (`baseballsavant.mlb.com`). **Seasons:** the 2026 regular season (played), 2025 (used to steady early-2026 stats with a gradual fade over the first 6 weeks), and the published 2027 schedule (not yet played).

## How the app uses it

- **"Stats as of the game"**: the per-game tables (`batting_lines`, `pitching_lines`, `statcast_*_game`) are summed over every game *before* the chosen date, so a June 16 plan never sees June 16 or later.
- **Who is available**: `roster_stints` says who was on a team's active roster on any date; `transactions` says why someone wasn't (injured list and reason, optioned, etc.).
- **Rates are computed, not stored**: tables keep raw counts and sums so any date range adds up correctly. For example, whiff % = `whiffs / swings` and wOBA = `woba_num / woba_den`.

## Planning 2027 games

The 2027 season hasn't been played, so a 2027 plan uses the same engine with three rules:
- **Stats:** the full 2026 season, and 2025 for players with no 2026 data. ("Everything before the game date" for a 2027 game is all of 2026.)
- **Rosters:** each team's active roster at the end of 2026. Players who ended 2026 on the injured list are included and flagged "assumed healthy, confirm with medical staff." Free agency and trades aren't known, so they aren't modeled.
- **Opposing starter:** a projection. The team's established starters (most 2026 starts first, plus half credit for 2025 starts) are cycled through its 2027 schedule, 5 or 6 deep to match the team's 2026 rotation.

## Reference tables

| Table | One row per | Key columns |
|---|---|---|
| `meta` | build fact | `key`, `value` (build time, seasons, opening day, sources) |
| `teams` | MLB team (30) | `team_id`, `name`, `abbrev`, `team_name`, `league`, `division`, `venue` |
| `players` | player in 2025 or 2026 | `player_id`, `full_name`, `primary_position`, `bat_side` (L/R/S), `pitch_hand` (L/R), `birth_date`, `mlb_debut`, `end_of_season_team_id` |
| `future_games` | scheduled 2027 regular-season game (2,430, published by MLB in July 2026) | `game_pk`, `season`, `game_date`, `game_number`, `home_team_id`, `away_team_id`, `venue`, `day_night`, `series_game_number` |
| `games` | completed 2026 regular-season game (2,429: BAL @ NYY on Sept 27 was cancelled and never made up, so those two teams played 161) | `game_pk`, `game_date`, `game_number` (doubleheaders), `home_team_id`, `away_team_id`, `home_probable_id`, `away_probable_id` (listed probable starters), `home_score`, `away_score`, `venue` |

## Availability

| Table | One row per | Key columns |
|---|---|---|
| `roster_stints` | unbroken stretch a player spent on a team's active roster (rebuilds the API's roster exactly on all 4,808 team-dates) | `team_id`, `player_id`, `position`, `start_date`, `end_date`. Active on date D means `start_date <= D <= end_date` |
| `transactions` | 2026 roster move | `txn_date`, `effective_date`, `team_id`, `player_id`, `type_code`, `description` (e.g. "placed on the 10-day injured list. Right hamstring strain.") |

## Per-game box scores (2026)

| Table | One row per | Key columns |
|---|---|---|
| `batting_lines` | player who batted in a game | `game_pk`, `game_date`, `team_id`, `player_id`, `lineup_slot` (1-9), `is_starter` (0 = sub), `start_position`, `positions` (every position played), `pa`, `ab`, `h`, `doubles`, `triples`, `hr`, `bb`, `ibb`, `k`, `hbp`, `sf`, `sh`, `r`, `rbi`, `sb`, `cs` |
| `pitching_lines` | pitcher who pitched in a game | `game_pk`, `game_date`, `team_id`, `player_id`, `appearance_order`, `is_starter`, `outs` (IP × 3), `pitches`, `bf`, `h`, `r`, `er`, `bb`, `k`, `hr`, `w`, `l`, `sv`, `hld`, `bs` |

These also power the rotation predictor (who started when, on how much rest), bullpen workload (pitches in recent days), the opponent lineup predictor, and the backtest (what the real manager did).

## Statcast rollups

| Table | One row per | Use |
|---|---|---|
| `statcast_pitcher_game` | 2026 game × pitcher × batter side (`stand` L/R) × `pitch_type` | Pitch arsenals, usage, velocity, whiffs, results vs lefties/righties |
| `statcast_batter_game` | 2026 game × batter × pitcher hand (`p_throws` L/R) × `pitch_group` | Platoon splits, how a hitter handles fastballs/breaking/offspeed |
| `statcast_pitcher_season` | 2025 season × pitcher × `stand` × `pitch_type` | Early-2026 fade |
| `statcast_batter_season` | 2025 season × batter × `p_throws` × `pitch_group` | Early-2026 fade |

**Pitch groups:** `FB` fastballs (4-seam, sinker, cutter), `BRK` breaking (slider, sweeper, curve, knuckle-curve, slurve), `OFF` offspeed (changeup, splitter, forkball), `OTH`/`UN` other or unclassified.

**Shared count columns:** `pitches`, `swings`, `whiffs`, `called_strikes`, `zone_pitches` (in the strike zone), `chase_swings` (swings at pitches outside it), `bip` (balls in play), `hard_hit` (95+ mph), `barrels`, `ev_n`/`ev_sum` (exit velocity), `pa`, `ab`, `h`, `tb`, `hr`, `bb`, `k`, `hbp`, `sf`, `woba_den`/`woba_num` (wOBA), `xwoba_num` (expected wOBA; same denominator), `rv_sum` (run value from the hitter's side; flip the sign for the pitcher). Pitcher tables add `velo_sum`/`velo_n` and `spin_sum`/`spin_n`.

## Season tables

| Table | One row per | Key columns |
|---|---|---|
| `season_hitting` | season × player (× team if traded) | Official 2025/2026 totals: `g`, `pa`, `ab`, `h`, `hr`, `bb`, `k`, `sb`, `avg`, `obp`, `slg`, `ops` |
| `season_pitching` | season × player (× team if traded) | `g`, `gs`, `outs`, `ip`, `bf`, `h`, `er`, `bb`, `k`, `hr`, `sv`, `hld`, `era`, `whip`, `pitches` |
| `sprint_speed` | season × player | `sprint_speed` (ft/sec), `hp_to_1b`, `competitive_runs`. Pinch-runner choices |
| `outs_above_average` | season × fielder | `position`, `outs_above_average`, `fielding_runs_prevented`. Defensive choices |
| `catcher_framing` | season × catcher | `pitches`, `framing_runs`, `strike_rate`. Catcher choice |

These leaderboards are full-season only (Savant doesn't publish them by date), so a June plan sees the full-2026 value. They measure stable skills (speed, range, framing), and this is listed as a known limitation.

## Data quality

`scripts/spot_check.py` compares this file to live published numbers (Stats API and Savant) and writes `evidence/tests/phase2_spot_checks.md`. Two cleaning rules came out of it:
- A suspended game (SF @ ATL, June 16 to 17) appears twice in the schedule under one `game_pk` and is stored once.
- Statcast logs automatic balls/strikes (intentional walks, pitch-clock violations) as rows. They are not counted as thrown pitches, but they still count toward the plate-appearance result.
