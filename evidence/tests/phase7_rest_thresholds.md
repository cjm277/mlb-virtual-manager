# Rest-day rule: thresholds from 2026 data

Runs of straight starts by 2026 regulars (100+ starts for one team) that ended with a game off (rest day, platoon sit or injury). Built by `scripts/rest_thresholds.py`.

| Group | Regulars | Runs | Median | 75th percentile | 90th percentile | Rule: rest suggested at |
|---|---|---|---|---|---|---|
| Catchers | 12 | 274 | 3 | 6 | 10 | **6 straight starts** |
| Everyone else | 182 | 2,574 | 4 | 10 | 21 | **10 straight starts** |

The rule fires at the 75th percentile: a run longer than three out of four real runs. It **suggests** rest; the Bench Coach picks the day, preferring one where the player's matchup is weak, so the day off costs the least. Real managers tend to rest on a schedule, regardless of the opponent.
