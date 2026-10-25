# Win model: is the staff's plan more likely to win than the manager's?

Generated 2026-10-24 22:02 by `scripts/win_impact.py`. Per-game numbers: `evidence/logs/win_impact/results.json`; the plans and their audit trails: `evidence/logs/win_impact/plans/`.

**The question.** Given only what was known the day before the game, is the lineup and starting pitcher our staff chose analytically more likely to win than the lineup and starter the real manager chose? Both go through the same win model, with everything else held fixed: the opponent's real lineup and starter, both bullpens, and home field. Game results play no part in the comparison.

## The win model

1. **Each hitter's value:** his wOBA to date, regressed toward league average for small samples (trusted halfway at 200 PA), plus the league-typical platoon edge (+0.007 with it, -0.008 without; measured on 2025).
2. **Each starter's value:** his wOBA allowed to date, regressed the same way (halfway at 400 batters faced), and how deep he usually pitches (batters faced per start, regressed to the league's 21.4).
3. **Plate appearances:** each batting-order slot gets its league-average share (4.63 for the leadoff hitter down to 3.75 for the ninth), so the batting order counts. Each hitter faces the opposing starter for the share of the game that starter usually pitches, then a league-average bullpen.
4. **Runs:** expected wOBA above league average is turned into runs with the standard wOBA scale (1.2), around the league's 4.48 runs per team per game.
5. **Win probability:** runs scored and allowed go through Pythagenpat, the standard runs-to-wins formula, plus a standard home-field edge (54%).

Two sources of player value, reported side by side:
- **Season stats (independent):** steps 1 and 2 as described. The app never optimizes these numbers directly, so this column is the fair test.
- **The app's matchup engine (its own lens):** a hitter's plate appearances against the starter are valued by the app's expected xwOBA for that hitter against that starter's pitch mix. Everything else is the same.

## Result

150 games: 5 per team, spread from mid-April to the last day of the 2026 season. The full staff built each plan exactly as the app does (142 were approved by the Manager). Our starting nine shared 7.0 players with the manager's on average, and our starter matched his in 63% of games.

| Average per game | Season stats (independent) | App's matchup engine |
|---|---|---|
| Win probability, manager's plan | 50.49% | 50.44% |
| Win probability, our plan | 50.60% | 51.54% |
| **Edge: lineup + starter** | **+0.11 pts** | **+1.10 pts** |
| 95% range (sampling) | -0.30 pts to +0.51 pts | +0.56 pts to +1.65 pts |
| Range across model assumptions | -0.08 pts to +0.46 pts | +1.00 pts to +1.27 pts |
| Edge from the lineup alone | -0.37 pts (-0.57 pts to -0.16 pts) | +0.06 pts (-0.26 pts to +0.38 pts) |
| Edge from the starter alone | +0.48 pts (+0.16 pts to +0.87 pts) | +1.04 pts (+0.60 pts to +1.55 pts) |
| **Wins per 162 games** | **+0.2** (-0.5 to +0.8) | **+1.8** (+0.9 to +2.7) |
| Games where our plan is better / worse | 43% / 53% | 63% / 35% |

"95% range (sampling)" is a bootstrap over the sampled games. "Range across model assumptions" re-runs the whole comparison under 27 settings: wOBA scale 1.1 / 1.2 / 1.3, hitter regression 100 / 200 / 800 PA, and pitcher regression 200 / 400 / 800 batters faced.

## Where the plans differ

Our nine differed from the manager's by 2.0 players per game.

| | Hitters we started instead | Hitters of his we benched |
|---|---|---|
| Season value (wOBA, regressed, with platoon edge) | 0.313 | 0.320 |
| Had the platoon edge against the opposing starter | 33% | 54% |
| App's matchup score against the opposing starter | 0.311 | 0.308 |
| Plate appearances behind the numbers | 190 | 206 |

35% of the hitters we benched were sitting for a suggested rest day (season value 0.328); the others were benched for matchups (season value 0.316). A rest day gives up a little today on purpose. Its payoff, fresher hitters later, is outside a one-game model.

## Robustness

| Plans included | Plans | Season stats: lineup + starter | lineup only | Matchup engine: lineup + starter | lineup only |
|---|---|---|---|---|---|
| All plans | 150 | +0.11 pts | -0.37 pts | +1.10 pts | +0.06 pts |
| Excluding plans that started a possibly hurt player | 103 | +0.19 pts | -0.41 pts | +1.12 pts | +0.08 pts |
| Same starting pitcher as the real team | 95 | -0.32 pts | -0.32 pts | +0.15 pts | +0.15 pts |
| Plans the Manager approved | 142 | +0.15 pts | -0.37 pts | +1.18 pts | +0.05 pts |
| Plans with no rest-day benching | 72 | +0.15 pts | -0.09 pts | +1.27 pts | +0.51 pts |
| Our starter = the real team's next starter, moved up | 39 | +1.36 pts | -0.48 pts | +3.91 pts | -0.09 pts |
| Our starter differs, and was not the next starter | 16 | -0.38 pts | -0.35 pts | -0.07 pts | -0.09 pts |

"Possibly hurt": 47 plans started a hitter who did not play at all that day or in the team's next game. The data only knows injured-list moves, not day-to-day knocks.

## Appendix A: are the model's probabilities realistic?

The model applied to every 2026 game with the real lineups and starters. Predicted home win probability vs how often the home team won, by fifth of predictions:

| Model says (average) | Home team won | Games |
|---|---|---|
| 46.4% | 45.9% | 486 |
| 51.2% | 49.2% | 486 |
| 54.2% | 55.5% | 485 |
| 56.8% | 50.8% | 486 |
| 61.5% | 63.0% | 486 |

Brier score 0.2464 vs 0.2493 for "54% for every home team". Baseball is close to a coin flip game by game, so realistic probabilities stay in a narrow band. That's why a 1-point edge per game is worth a meaningful number of wins over 162.

## Appendix B: do the inputs carry real information?

A logistic regression of 2026 results on the three edges at once (log-odds per .010; |z| above 2 means clearly not zero):

| Input | Coefficient | z |
|---|---|---|
| Home field | 0.112 | 2.7 |
| Lineup edge, season stats | 0.039 | 0.9 |
| Starter edge, season stats | 0.105 | 4.7 |
| Matchup edge, the app's engine | 0.005 | 0.3 |

Correlation between the matchup edge and the starter edge: 0.53.

## What the numbers say

**1. Overall, by independent numbers, the plans are a match for real MLB managers, not yet a clear win.**
- On season stats, our plan's win probability is +0.11 points per game, about **+0.2 wins per 162**. The 95% range is −0.5 to +0.8 wins, and every one of the 27 assumption settings lands between −0.1 and +0.7 wins.
- By the app's own matchup engine, the edge is +1.8 wins per 162 (+0.9 to +2.7). But Appendix B shows that, in one season of data, the pitch-type matchup score adds no information about who wins once season quality is known. So the independent column is the one to quote.

**2. The edge comes from the starting pitcher, and it's real.**
- Starter choice alone is worth **+0.48 points per game (+0.16 to +0.87)**, a range that clears zero.
- Almost all of it comes from one move: starting the team's *next* starter a day early when he's the better pitcher (39 of 150 games). Those games average **+1.36 points** on season stats.
- When our starter is the same as the real one, the starter edge is zero by definition.
- What a one-game model can't price: moving a pitcher up shortens his rest and skips a turn. The edge is genuine per game, but a season-long rotation that does this every time would need its own test.

**3. The lineups cost a little, for two measurable reasons.**
- Lineup choice alone is **−0.37 points per game (−0.57 to −0.16)**, about −0.6 wins per 162.
- **Rest days (deliberate).** 35% of the hitters we bench are sitting for rest, and they are good hitters (.328 season value). In plans with no rest-day benching, the lineup gap shrinks to −0.09 points, which is even. The rest rule spends a little of today's win probability on fresher players later, which this model can't see.
- **Trusting pitch-type matchups over the platoon edge.** The hitters we bench for matchups had the platoon edge 54% of the time; the ones we start instead, 33%. The engine prefers a hitter who looks good against this pitcher's pitch mix. But 2026 data says the pitch-type signal carries no extra information about winning beyond plain quality (Appendix B, z = 0.3), while the platoon edge is a well-measured effect.

**4. A claim the numbers support today:** "Across 150 real 2026 games, an AI staff working only from data available the day before planned games that were as likely to win as the plans of real MLB managers (within about ±0.8 wins a season). Each plan took under a minute and cost under 2 cents. Its starting-pitcher calls were measurably better (+0.5 win-probability points per game). Its lineups gave up a little, mostly by resting regulars on purpose."

**5. The numbers point to where a real edge would come from:**
- **Build the lineup from the win model, not the LLM's judgment.** Code would choose the nine and the order that maximize expected runs, with the platoon edge and rest days priced in, and the staff would explain the choice. If the lineup edge moved from −0.37 to zero while the starter edge stays, the total would be about +0.8 wins per 162.
- **Shrink the pitch-type matchup score toward season quality** before the Bench Coach sees it, so a noisy signal can't override a reliable one.
- Both are testable with this same setup (`scripts/win_impact.py`) at about $2.50 for another 150 plans.

**How this was kept honest:**
- **Nothing from the game itself feeds the comparison.** Both plans are scored with stats from before first pitch.
- **No hand-picked games.** The sample is 5 per team, spread evenly over the season (seed 409).
- **Results checked from two independent angles.** The model was re-run under 27 different settings and with 1,000 bootstrap resamples.
- **Possibly hurt starters excluded.** Dropping the 47 plans that started a hitter who may have been hurt changes the overall result by less than 0.1 points.

**Follow-up (done):** the win-model lineup and the matchup shrink were built and re-scored on the same 150 games. See `evidence/tests/win_model_lineup.md`: about +1.5 wins per 162 on the independent lens (+0.9 to +2.2).
