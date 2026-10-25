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
