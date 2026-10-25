# Which pre-game numbers best predict a hitter against today's starter?

43,409 2026 hitter-games. Each candidate is calibrated on April-June and scored on July-September (PA-weighted mean squared error vs how the hitter actually hit against that starter's hand). "Signal" is how much of the error a league-average guess leaves that the candidate removes. Single games are very noisy, so every candidate's share is small; what matters is the ranking. Script: `scripts/value_model_search.py`.

| Rank | Hitter value | Regress hitter at | Platoon | Starter value | Regress starter at | Signal vs league average |
|---|---|---|---|---|---|---|
| 1 | xwoba | 200 PA | own | woba | 400 BF | 0.606% |
| 2 | xwoba | 100 PA | own | woba | 200 BF | 0.601% |
| 3 | xwoba | 100 PA | own | woba | 400 BF | 0.601% |
| 4 | xwoba | 200 PA | own | blend | 400 BF | 0.596% |
| 5 | xwoba | 100 PA | own | blend | 200 BF | 0.596% |
| 6 | xwoba | 200 PA | own | woba | 200 BF | 0.595% |
| 7 | xwoba | 200 PA | own | blend | 200 BF | 0.592% |
| 8 | xwoba | 50 PA | own | woba | 200 BF | 0.591% |
| 9 | xwoba | 400 PA | own | woba | 400 BF | 0.590% |
| 10 | blend | 200 PA | own | woba | 400 BF | 0.590% |
| ... | | | | | | |
| 261 (the win model used so far) | woba | 200 PA | league | woba | 400 BF | 0.424% |
| 360 (worst) | woba | 800 PA | league | xwoba | 100 BF | 0.305% |

**Chosen for the app's lineup model:** hitter xwoba regressed at 200 PA, own platoon split, starter woba regressed at 400 batters faced. It removes 1.43x as much error as the version used so far.
