# Lineup model parameters, measured on 2026

Every 2026 start: 43,409 hitter-games, 142,076 plate appearances against the opposing starter's hand. Outcome: how the hitter actually hit (wOBA) that day. Weighted least squares, 95% ranges from 500 bootstrap resamples. Script: `scripts/lineup_params.py`.

| Pre-game input | Effect on how he actually hit | 95% range |
|---|---|---|
| Season value in the win model (per 1.000) | 0.700 | 0.597 to 0.796 |
| Pitch-type matchup adjustment (per 1.000) | -0.040 | -0.220 to 0.135 |
| Past the rest-day threshold (27.7% of starts) | +0.0145 wOBA | +0.0084 to +0.0205 |

**Matchup shrink:** a point of pitch-type adjustment is worth -0.06 of a point of season value (95% range -0.34 to 0.19). The app now keeps 0% of the adjustment (clipped to 0-100%).

**Fatigue cost:** a hitter past the threshold hits +0.0145 wOBA against his pre-game value. The lineup model charges that against a tired hitter's value for the day.
