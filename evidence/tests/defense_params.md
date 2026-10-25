# Does defense earn its place in the win model?

Every 2026 team-game (4,858). Outcome: runs allowed. Defensive ratings use 2023-2025 only (completed seasons before each game, weighted toward 2025), so nothing from 2026 leaks in. Least squares; 95% ranges from 1,000 bootstrap resamples. Script: `scripts/defense_params.py`.

| Pre-game input (runs per game) | Effect on runs allowed | 95% range |
|---|---|---|
| Opponent lineup's expected runs vs our starter | +1.449 | +1.098 to +1.807 |
| Our fielders' range (fielding runs prevented at their positions, 2023-2025 rating) | -1.151 | -2.240 to +0.057 |
| Our catcher's framing (2023-2025 rating) | -1.309 | -2.390 to -0.178 |

A coefficient of −1 means a run of rated defense saves a full run; 0 means it predicts nothing. Fielding varies by ±0.07 runs per game across real lineups (one standard deviation), framing by ±0.08.

**Out of sample (fit April-June, test July-September):** mean squared error of runs allowed 10.2222 without defense vs 10.2261 with it.

That test has little power: defense moves runs allowed by only a few hundredths of a run per game, against a game-to-game spread of about ±3 runs. The stronger evidence that the ratings carry real skill is that they predict the next season's defense (`evidence/tests/defense_rating_search.md`).

**Weights used by the win model and the lineup optimizer:** fielding 1.00, framing 1.00. A rated run saved is worth one run when the measured range includes 1, as both do here.
