# Pricing fielders with a thin record at the position (fitted on 2025, no 2026 data)

Every 2025 player-position: the app's pre-2025 rating (2023-24 only) against what he did there in 2025, innings-weighted, by how established he was there. Script: `scripts/defense_caution.py`. Runs saved per game.

| Group | Player-positions | Mean rating | Mean 2025 result | Intercept | Slope | 2026 fit (comparison only): intercept / slope |
|---|---|---|---|---|---|---|
| established | 407 | +0.0081 | +0.0025 | -0.0057 (-0.0123 to +0.0008) | 1.02 (0.80 to 1.23) | -0.0019 / 0.95 |
| part-time | 519 | -0.0027 | -0.0041 | -0.0010 (-0.0112 to +0.0085) | 1.16 (0.63 to 1.72) | -0.0134 / 1.56 |
| new | 387 | -0.0138 | -0.0121 | -0.0120 (-0.0352 to +0.0104) | 0.01 (-1.27 to 1.34) | +0.0081 / 1.81 |

**Small samples look far worse than they are.** Player-positions with fewer than 100 innings that season:

| Group | Season | n | Mean result, each player counted once | Mean result, innings-weighted |
|---|---|---|---|---|
| established | 2025 | 111 | -0.031 | -0.043 |
| established | 2026 | 151 | -0.075 | -0.043 |
| part-time | 2025 | 342 | -0.129 | -0.030 |
| part-time | 2026 | 338 | -0.142 | -0.065 |
| new | 2025 | 273 | -0.159 | -0.053 |
| new | 2026 | 266 | -0.192 | -0.068 |

Counted once each, short stints average far below zero (-0.13 to -0.19 runs a game for part-time and new fielders). Weighted by innings the gap shrinks by half or more but stays clearly negative (-0.03 to -0.07), well below their ratings, in both seasons. Two things produce this, and the data can't fully separate them: a fielder who starts badly at a position is moved off it, freezing a bad small sample (a measurement effect); and managers see things the ratings don't, so short stints go to fielders who really are worse there. Note the short stint is itself an outcome: before the game no one knows whose stint will be short, which is why the groups above, by pre-game experience and all innings, are what the optimizer can use.

**Used by the optimizer** (data/lineup_params.json `defense_caution`, slope capped at 1): calibrated = intercept + slope x rating for each group; strict = established as calibrated, part-time and new at their group's mean.
