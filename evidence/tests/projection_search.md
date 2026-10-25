# Marcel-style projections: regress toward the player's own track record (2025, 2024), not only the league

43,409 2026 hitter-starts. Calibrated on April-June, scored on the July-September hold-out (PA-weighted mean squared error vs how each hitter actually hit against that starter's hand). "Signal" = share of a league-average guess's error that the candidate removes; single games are very noisy, so shares are small and the ranking is what matters. "Calibration slope" = how much of a rated difference shows up in the hold-out (1 = fully). Script: `scripts/projection_search.py`.

Marcel pools the seasons, `(2026 + w x 2025) counts`, then regresses the pool toward league at k plate appearances. The app's model so far used the fade blend: 2025 fades out over the first six weeks, then only 2026-to-date counts.

## Result

| Model | Signal on Jul-Sep hold-out | Calibration slope |
|---|---|---|
| Current app model (fade blend; hitter xwOBA k=200; own platoon at 400 PA; starter wOBA k=400) | 0.603% | 0.91 |
| **Chosen: Marcel** (hitter xwoba, 2025 weight 0.75, 2024 weight 0.0, k=100; own platoon, 2025 weight 0.5, regressed at 200 PA; starter woba, 2025 weight 0.75, 2024 weight 0.0, k=200) | 0.740% | 0.74 |
| Same, with 2024 added for hitters at its best weight (0.25); rejected, adds under 0.01 points | 0.741% | 0.74 |

The chosen model removes **1.23x** as much hold-out error as the current one.

## Hitter part (platoon and starter parts as chosen)

| Hitter value | 2025 weight | 2024 weight | Regress at (PA) | Signal | Slope |
|---|---|---|---|---|---|
| xwoba | 0.75 | 0.25 | 100 | 0.741% | 0.74 |
| xwoba | 0.75 | 0.0 | 100 | 0.740% | 0.74 |
| xwoba | 1.0 | 0.25 | 100 | 0.740% | 0.72 |
| xwoba | 1.0 | 0.0 | 100 | 0.738% | 0.72 |
| xwoba | 0.75 | 0.25 | 50 | 0.738% | 0.69 |
| xwoba | 0.5 | 0.25 | 100 | 0.738% | 0.76 |
| xwoba | 0.75 | 0.0 | 50 | 0.737% | 0.68 |
| xwoba | 1.0 | 0.25 | 50 | 0.736% | 0.67 |

Same metric, 2025 weight and k as chosen, by 2024 weight:

| 2024 weight | Signal | Slope |
|---|---|---|
| 0.0 | 0.740% | 0.74 |
| 0.25 | 0.741% | 0.74 |
| 0.5 | 0.734% | 0.72 |
| 0.75 | 0.725% | 0.71 |

## Platoon part: how hard to regress a hitter's own split

| 2025 weight | Regress at (PA vs that hand) | Signal | Slope |
|---|---|---|---|
| 0.5 | 200 | 0.686% | 0.77 |
| 0.75 | 200 | 0.684% | 0.76 |
| 0.25 | 200 | 0.681% | 0.78 |
| 1.0 | 200 | 0.680% | 0.75 |
| 0.5 | 100 | 0.679% | 0.72 |
| 0.75 | 400 | 0.677% | 0.79 |
| 1.0 | 400 | 0.677% | 0.78 |
| 0.5 | 400 | 0.676% | 0.80 |
| 0.0 | league split only | 0.590% | 0.82 |

## Starter part

| Starter value | 2025 weight | 2024 weight | Regress at (BF) | Signal | Slope |
|---|---|---|---|---|---|
| woba | 0.75 | 0.0 | 200 | 0.741% | 0.74 |
| woba | 1.0 | 0.0 | 200 | 0.740% | 0.72 |
| woba | 1.0 | 0.0 | 400 | 0.736% | 0.77 |
| woba | 0.75 | 0.25 | 200 | 0.736% | 0.75 |
| woba | 0.75 | 0.0 | 400 | 0.736% | 0.79 |
| woba | 0.5 | 0.0 | 200 | 0.735% | 0.76 |
| woba | 1.0 | 0.25 | 200 | 0.735% | 0.73 |
| woba | 0.75 | 0.0 | 100 | 0.733% | 0.69 |

Same metric, 2025 weight and k as chosen, by 2024 weight:

| 2024 weight | Signal | Slope |
|---|---|---|
| 0.0 | 0.741% | 0.74 |
| 0.25 | 0.736% | 0.75 |
| 0.5 | 0.727% | 0.75 |
| 0.75 | 0.717% | 0.73 |
