# Is the win model really worth +2.4 wins a season? A verification

Generated 2026-10-25 00:21 by `scripts/value_verification.py` (no LLM calls, no new plans; the same 150 v3 plans as `win_model_defense.md`). Numbers: `evidence/logs/win_impact/value_verification.json`. Wins are per 162 games; a win-probability point per game is 1.6 wins a season.

## The claim, split into its pieces (season-stats lens, as reported)

| Piece | Wins per 162 | 95% range (games bootstrap) |
|---|---|---|
| Lineup: offense | +0.2 | -0.1 to +0.5 |
| Lineup: defense (fielding + framing) | +1.4 | +1.2 to +1.6 |
| Starter (mostly moving the next starter up a day) | +0.8 | +0.3 to +1.4 |
| **Total** | **+2.4** | +1.8 to +3.0 |

The lineup's offense is a small part of the claim. Most of it is defense and the starter.

## Check 1: circularity

Defense counts the same way in the lens and in the optimizer: the same 2023-25 ratings, the same 1.0 weight. So the defense piece, 58% of the claim, is the optimizer graded on its own yardstick. The starter piece uses the same starter rating (wOBA allowed, regressed at 400 batters faced) in both. Only the hitter values differ (lens: wOBA with the league platoon split; optimizer: xwOBA with the hitter's own split), and those two share the same plate appearances.

**Independent-data lens.** The same plans re-scored with what every player did *after* the game: hitters' and starters' rest-of-2026 wOBA, and fielders' and catchers' 2026 defense instead of the 2023-25 ratings. None of this data was available to the optimizer, so picking players on lucky numbers can't inflate it. Its own noise is large.

| Piece | Claimed | Independent lens, unregressed | Independent lens, regressed |
|---|---|---|---|
| Lineup: offense | +0.2 | -0.6 (-2.2 to +1.0) | -0.4 (-0.9 to +0.1) |
| Lineup: defense | +1.4 | -0.5 (-1.4 to +0.4) | -0.6 (-1.5 to +0.3) |
| Starter | +0.8 | +2.2 (+0.0 to +4.5) | +1.0 (+0.2 to +2.0) |
| **Total** | +2.4 | +1.1 (-1.7 to +4.1) | +0.0 (-1.3 to +1.4) |

## Check 2: does the lens predict real runs?

Every 2026 team-game (4,858), real lineups and starters. Runs actually scored are regressed on the lens's three parts, with batting-team and fielding-team fixed effects. Only game-to-game changes within a team (who plays, who starts) identify the slopes, and those are the choices the app makes. A slope of 1 means the lens's run estimates are right on average, and 0 means they predict nothing. The lens's parameters were set before 2026 (2025 league numbers, standard constants), so August-September is a clean hold-out. The one exception is the defense weight of 1.0, which was set from all 2026 games.

| Lens part (runs) | Within-team spread (SD) | Slope, all 2026 | Slope, Aug-Sep only | Slope without team effects |
|---|---|---|---|---|
| Our lineup's offense | 0.167 | -0.25 (-0.78 to +0.26) | -0.73 (-1.94 to +0.63) | +0.64 |
| Opposing starter's quality | 0.259 | +0.76 (+0.44 to +1.11) | +0.70 (+0.16 to +1.26) | +1.22 |
| Opposing defense (expect −1) | 0.066 | -0.23 (-1.85 to +1.14) | +0.49 (-1.95 to +3.57) | -1.21 |

Single games are noisy (about ±3 runs), so these slopes are imprecise. Player-level checks have far more data. Each one asks how much of a rated difference shows up later, in data the rating never saw:

| Rating | What it predicts | Slope (1 = fully realized) | 95% range |
|---|---|---|---|
| Lens hitter value (wOBA, regressed at 200 PA) | His wOBA over the rest of 2026 (38,917 starts, 567 hitters) | 0.40 | 0.25 to 0.52 |
| Fielding rating, 2023-25 | His 2026 runs prevented at that position (1325 player-positions) | 1.01 | 0.81 to 1.20 |
| Framing rating, 2023-25 | His 2026 framing (56 catchers) | 0.71 | 0.40 to 1.21 |

Fielding by how established the player was at the position (pre-game information), innings-weighted:

| Group | Player-positions | Mean rating | Mean 2026 result | Intercept | Slope |
|---|---|---|---|---|---|
| part-time there (1-299 innings) | 493 | +0.001 | -0.012 | -0.013 (-0.025 to -0.003) | 1.56 (0.86 to 2.38) |
| established (300+ innings there in 2023-25) | 452 | +0.008 | +0.006 | -0.002 (-0.009 to +0.005) | 0.95 (0.72 to 1.16) |
| new to the position | 380 | -0.013 | -0.016 | +0.008 (-0.011 to +0.032) | 1.81 (0.79 to 3.05) |

## Check 3: the starter over a full season

57 of 150 plans changed the starter; 40 moved the team's next starter up (worth +0.8 wins of the claim), and the other 17 were worth -0.0. Days of rest for the starters we chose: 2: 1, 3: 1, 4: 35, 5: 7, 6: 1, 8: 2, 10: 1, 21: 1, 35: 1, 36: 1, 60: 1.

A one-game comparison treats today's start as free. It isn't: the pitcher we move up is not available for the game he would have started, and someone worse starts that one. **Season replay:** every team's 2026 schedule, replayed with the rule "start the best-rated starter on the active roster with 4+ days of rest". Each choice uses up that pitcher's rest for the games that follow. The "one game at a time" column applies the same rule to the real rest state each day, which is what the 150-game analysis credits.

| Rule | Starts changed | Runs saved per game, one game at a time | Runs saved per game, season replay | Share kept | Same, judged on rest-of-season results | Extra starts for each team's top gainer |
|---|---|---|---|---|---|---|
| No workload cap | 81% | 0.145 | 0.064 | 44% | 0.044 vs 0.019 | +7.4 |
| At most 2 starts more than he really made | 78% | 0.145 | 0.041 | 28% | 0.044 vs 0.014 | +2.8 |
| No more starts than he really made | 73% | 0.145 | 0.024 | 16% | 0.044 vs 0.014 | +2.5 |

Does 4 days of rest hurt? Starters' runs allowed per start vs their own 2026 average: 4 days -0.03 (±0.05, 1338 starts), 5 days +0.08 (±0.04), 6-10 days +0.02 (±0.07). There's no measurable same-day penalty. The real costs of more starts for the best starters are innings limits and injury risk, which this data can't price.

## Check 4: sensitivity to the defense weight and to rest days

| Defense weight in the lens (plans unchanged) | 0 | 0.5 | 1.0 (as used) |
|---|---|---|---|
| Total edge, wins per 162 | +1.0 | +1.7 | +2.4 |

**Rest days.** 18 of 150 plans started a player the Team Doctor flagged for rest, where the real manager benched him. Those lineups account for +0.3 wins of the claim. If every one of those rest days has to be taken on another day anyway (rest is zero-sum over a season), the total falls to +2.1. The same-day fatigue cost measured in 2026 was zero (`lineup_params.md`), but that test can't see injuries or late-season wear.

## Check 5: the interval

The published +1.8 to +3.0 is a bootstrap over the 150 games with the lens held fixed (+1.7 to +3.1 here). It covers which games were sampled, but not whether the lens's numbers are right. The verified estimate below scales each piece by what held-out data says it is worth, and its interval redraws the games and every scaling factor together (2,000 draws):

- **Offense** × the hitter-value slope (bootstrap by player).
- **Defense**, re-valued at what 2026 says each fielder's rating is worth: intercept and slope by group, bootstrap draws. The framing gain is then × the framing slope (drawn across its range) × a catcher-workload factor (0.60-0.90). The plans used the team's best-framing catcher in 76% of games (real managers: 43%), but no 2026 team's main catcher started more than 75% of its games, and the 90th percentile was 68%.
- **Starter** × the within-team starter slope (bootstrap draws) × the share a season replay keeps (28%-44%).

| Piece | Claimed | Verified |
|---|---|---|
| Lineup: offense | +0.2 | +0.1 |
| Lineup: defense | +1.4 | +1.1 |
| Starter | +0.8 | +0.2 |
| Interaction (lineup × starter) | +0.0 | +0.0 |
| **Total, wins per 162** | **+2.4** (+1.8 to +3.0) | **+1.4** (+1.1 to +1.9 within the calibration model) |
| **Honest range, adding model uncertainty** | | **+0.5 to +1.9** |

Within the calibration model the edge is above zero in 100% of draws. That model has one weak spot. It values fielding by how well the ratings predict 2026 defense *across all players*, where they hold up (slope about 1). But the direct check on *these* plans' fielders (Check 1) doesn't show the fielding gain at all. That check is noisy and has a selection problem: players who got few 2026 innings at a position often lost them by fielding badly. Still, it is a real warning. So the honest range runs down to a **floor of +0.5 wins**: the pieces that the direct check on these same plans confirms (catcher framing, cut for catcher workload, and the starter after the season replay), with fielding and offense counted at zero.

## Check 6: expected value in dollars

Every figure here is an estimate built on the stated assumptions. All of them start from the verified wins (+1.4; conservative low end +0.5, the floor), never the original +2.4. Two views of the same wins follow: what the market charges for a win, and what the wins do to playoff odds. They are alternatives, not additions, because the market price of a win already reflects the revenue that winning brings.

### The headline: value to ONE team that adopts first

The measured edge is against what real 2026 managers actually did. So it is already a first-mover figure: one team using the app while the other 29 keep managing as they do today.

**Per season, in expectation** ($10M per win; $30M per playoff berth to the club):

| View | At the verified estimate | At the conservative low end (the floor) |
|---|---|---|
| Market price of the wins | **$13.8M** | $5.1M |
| Playoff odds, typical team (talent drawn from the league spread) | $1.3M (+4.4 pts) | $0.5M (+1.8 pts) |
| Playoff odds, bubble team (84-win talent) | $2.2M (+7.4 pts) | $0.8M (+2.6 pts) |

**Over a head start**, cumulative and undiscounted, if rivals copy the approach. With the original Moneyball, the market's under-pricing of on-base percentage was found to have largely corrected by 2004, the season after the book (Hakes & Sauer, *Journal of Economic Perspectives*, 2006). So fast copying is the realistic case. The methods here (defense, framing, rotation use) are already known to front offices, which argues for fast copying too:

| Copying speed | Measure | 1 season | 2 seasons | 3 seasons |
|---|---|---|---|---|
| Fast copying (edge halves each season, like Moneyball's OBP edge) | market, verified | $13.8M | $20.7M | $24.1M |
| Fast copying (edge halves each season, like Moneyball's OBP edge) | market, low end | $5.1M | $7.7M | $9.0M |
| Fast copying (edge halves each season, like Moneyball's OBP edge) | playoffs bubble, verified | $2.2M | $3.3M | $3.9M |
| Fast copying (edge halves each season, like Moneyball's OBP edge) | playoffs bubble, low end | $0.8M | $1.2M | $1.4M |
| Slow copying (edge keeps 75% each season) | market, verified | $13.8M | $24.1M | $31.9M |
| Slow copying (edge keeps 75% each season) | market, low end | $5.1M | $9.0M | $11.9M |
| Slow copying (edge keeps 75% each season) | playoffs bubble, verified | $2.2M | $3.9M | $5.1M |
| Slow copying (edge keeps 75% each season) | playoffs bubble, low end | $0.8M | $1.4M | $1.8M |

**Market price of a win.** Teams pay roughly $8-12M per win (WAR) in free agency: about $8M per win in FanGraphs-based estimates, and about $8.3M for hitters and $11.6M for pitchers in an informal 2025 count. The verified wins, priced like free-agent wins, per season:

| $ per win | Low end | Verified | High end |
|---|---|---|---|
| $8M | $4.1M | **$11.0M** | $14.9M |
| $10M | $5.1M | **$13.8M** | $18.6M |
| $12M | $6.2M | **$16.6M** | $22.3M |

**Playoff odds.** Simulated league: 30 teams, two leagues of three five-team divisions. Team talent ~ Normal(81, 9.5) wins, so with luck the spread of records is about ±11.5, roughly MLB's recent spread. Each season is Binomial(162). Six teams per league qualify: three division winners and three wild cards. Then we add the verified wins to one team of a given talent. A berth is valued at $15M, $30M and $50M to the club after revenue sharing (48% of net local revenue is pooled). That covers the home playoff gate (a Wild Card series host keeps roughly $5-15M), plus the following season's lift in attendance, sponsorship and local media. An older estimate puts that lift at 20-30% of local revenue; a 2023 World Series run was put at $30-40M.

| Team situation | Playoff odds today | Added by the verified wins (low / mid / high) | Expected $ at $15M / $30M / $50M per berth (mid wins) |
|---|---|---|---|
| Rebuilding (72-win talent) | 6% | +0.7 / +2.3 / +3.4 pts | $0.3M / $0.7M / $1.1M |
| Fringe (78) | 21% | +2.1 / +5.7 / +7.8 pts | $0.9M / $1.7M / $2.9M |
| Bubble (84) | 50% | +2.6 / +7.4 / +9.9 pts | $1.1M / $2.2M / $3.7M |
| Bubble+ (87) | 65% | +2.6 / +6.6 / +8.6 pts | $1.0M / $2.0M / $3.3M |
| Likely (90) | 79% | +1.7 / +4.8 / +6.3 pts | $0.7M / $1.5M / $2.4M |
| Lock (96) | 94% | +0.9 / +1.8 / +2.3 pts | $0.3M / $0.6M / $0.9M |

For comparison, the original +2.4 claim would add +4.3 pts (rebuilding), +10.3 pts (fringe), +12.5 pts (bubble), +10.9 pts (bubble+), +8.0 pts (likely), +2.9 pts (lock) to playoff odds.

### The whole league

Wins are zero-sum: every game has one winner, so the league's 2,430 wins stay 2,430 whatever tools teams use.

- **One early adopter** (above): it gains about +1.4 wins a season, taken from the other 29 teams (about 0.05 wins each). That is the only case where the app's value shows up as wins.
- **Every team adopts:** the edges cancel. Each team's plan improves, but so does its opponent's, and league-wide wins can't rise. Expected wins per team go back toward 81, and the value in wins shrinks toward zero. What remains is cost and time: a full game plan costs about $0.019 in model calls, about $3 per team-season (Phase 8), against hours of staff preparation. That is a real saving, but it is measured in staff hours, not wins.
- **What a team might pay (licensing view, kept modest):** a buyer would pay only a slice of the value it expects, because rivals can copy the methods (they are public), and its own analysts could rebuild much of this. At 10%-20% of the expected first-mover value, that is roughly $0.5M-$2.8M per team per season, falling as adoption spreads. This is an illustration, not a market quote.

## With the opposing starter known

In the 150 v3 plans the code built our lineup against the *predicted* opposing starter (the rotation model). MLB announces probable starters a day or two ahead, so a real club would usually know. To test what that is worth, the lineup was rebuilt with the same optimizer (`winmodel.best_lineup`: same pre-game data, same Team Doctor OUT list, rest days and defense as usual) against the starter who actually pitched. Our own starter is kept as in the plan. No LLM calls; the app is unchanged.

The prediction was right in 114 of 150 games, and the hand was right in 136. 36 were wrong, 22 of them with the same hand. Knowing the starter changed the model lineup in 20 games (20 of the wrong-prediction games, 2.9 players on average there).

Edge vs the real manager in wins per 162, with 95% ranges. "Verified" is the calibrated estimate from Check 5, with its interval redrawing games and scaling factors; "season lens" is the original yardstick.

| Version | Verified: lineup + starter | Verified: lineup only | Season lens: lineup + starter |
|---|---|---|---|
| (b) The plan as built (predicted starter) | +1.38 (+1.05 to +1.81) | +1.15 (+0.88 to +1.52) | +2.38 (+1.77 to +3.04) |
| (b') Model lineup vs the predicted starter, rebuilt now | +1.41 (+1.08 to +1.83) | +1.18 (+0.91 to +1.55) | +2.46 (+1.84 to +3.18) |
| (c) Model lineup vs the known starter | +1.43 (+1.10 to +1.84) | +1.20 (+0.92 to +1.55) | +2.51 (+1.85 to +3.18) |

(a), the real manager, is the zero line. (b') isolates the effect of knowing the starter from the few plans where the staff edited the model lineup.

**Gain from knowing the starter, (c) minus (b'), paired on the same games:**

| Games | n | Verified | Season lens | (c) minus (b), the plan as built, verified |
|---|---|---|---|---|
| All 150 games | 150 | +0.01 (-0.02 to +0.05) | +0.05 (-0.02 to +0.11) | +0.05 (+0.00 to +0.10) |
| Predicted starter wrong | 36 | +0.06 (-0.07 to +0.20) | +0.20 (-0.05 to +0.44) | +0.10 (-0.04 to +0.25) |
| Wrong, other hand | 14 | +0.22 (-0.07 to +0.54) | +0.63 (+0.16 to +1.14) | +0.28 (-0.04 to +0.59) |
| Predicted starter right | 114 | +0.00 (+0.00 to +0.00) | +0.00 (+0.00 to +0.00) | +0.03 (+0.00 to +0.08) |

**In dollars** (same assumptions as Check 6): +0.01 wins a season is about $0.1M at $10M per win ($0.1M-$0.2M at $8-12M), or +0.04 pts of playoff odds for a typical team ($0.01M at $30M per berth) and +0.08 pts for a bubble team ($0.02M). Subgroup rows are per 162 games *of that kind*; a season has only the all-games share of them.

**What it means.**

- **Knowing the starter adds almost nothing:** +0.01 (-0.02 to +0.05) wins a season on the verified estimate, and the range includes zero.
- **Why it's small:**
  - The rotation model is already right in 76% of games, and right on the hand in 91%.
  - In 22 of the 36 misses, the wrong guess throws with the same hand, so the platoon-driven lineup barely changes.
  - The lineup's offense is a small part of the edge anyway. Most of the edge is defense and the starter, which don't depend on who pitches against us.
- **Where it matters:** the gain concentrates where expected, in the 14 games where the guess had the wrong hand. Even there it is a few tenths of a win per 162 such games, and they are under a tenth of the schedule.
- **Decision: not adopted. The app is deliberately predictive.** It keeps predicting the opposing starter from the rotation and does not read MLB's announced probables. Given how little knowing the starter adds, that choice costs about nothing in wins.

## Valuation to an MLB team (lineup insight)

What the program is worth to one club for its **lineup insight alone**: which nine to play, where to play them, and in what order, counting offense and defense. The starter-choice piece is left out and listed separately as an extra. All figures use the verified (calibrated) estimate from Check 5 on the 150 v3 plans, the lineup as built, against the real managers. They are a first-mover value: one team using it while the others manage as today. No LLM calls; the app is unchanged.

**Wins per 162 games:**

| Piece | Wins | 95% range |
|---|---|---|
| Offense (who bats, and the batting order) | +0.07 | -0.05 to +0.19 |
| Defense (fielding +0.79 + catcher framing +0.29) | +1.08 | +0.81 to +1.45 |
| **Lineup insight, total** | **+1.15** | **+0.86 to +1.54** |
| Conservative floor: framing only (after the catcher-workload cut), fielding and offense at zero | +0.29 | |
| *Extra, not included above: the starter choice (after the season replay)* | *+0.22* | |

The floor exists because the direct check on these same plans' fielders, scored on what they did after the game, did not confirm the fielding gain (Check 1). The calibration across all 2026 fielders does confirm it.

**Annual value at market prices** (free-agent $ per win, $M per season):

| $ per win | Low (95% low end) | Expected | High (95% high end) | Floor |
|---|---|---|---|---|
| $8M | $6.9M | **$9.2M** | $12.3M | $2.3M |
| $10M | $8.6M | **$11.5M** | $15.4M | $2.9M |
| $12M | $10.3M | **$13.8M** | $18.4M | $3.5M |

**Playoff-revenue view** (12-team format simulation as in Check 6; $30M per berth to the club after revenue sharing, with the $15M-$50M range in brackets):

| Team | Playoff odds added, expected | $ per season, expected | Playoff odds added, floor | $ per season, floor |
|---|---|---|---|---|
| Typical team (talent drawn from the league spread) | +3.7 pts | $1.1M ($0.6M-$1.9M) | +0.9 pts | $0.3M |
| Bubble team (84-win talent) | +6.1 pts | $1.8M ($0.9M-$3.1M) | +1.5 pts | $0.4M |

The market price and the playoff-revenue view are two readings of the same wins, so they are not added together. The market price is the ceiling, because it reflects what clubs pay for a win in free agency. The playoff view counts one revenue channel only.

**3-season head start, net present value** at 8%, valued at $10M per win, each season discounted from its end. The edge decays as rivals copy it:

| Copying speed | NPV, expected | NPV, floor |
|---|---|---|
| Fast copying (edge halves each season, like Moneyball's OBP edge) | $17.8M | $4.5M |
| Slow copying (edge keeps 75% each season) | $23.1M | $5.9M |

**A modest license price:** 10%-20% of year-1 value is $1.1M-$2.3M a season at the expected value, and $0.29M-$0.59M at the floor. That compares with about $3.14 a season in model calls per team (Phase 8). It is an illustration, not a market quote. A club pays only a slice because the methods are public and its own analysts could rebuild much of this, and the price falls as rivals adopt similar tools.

**Suggested report wording:**

> "Valued on its lineup insight alone (who plays, where, and in what order, counting offense and defense), the program adds about **+1.1 wins a season** to a single club that adopts it first (95% range +0.9 to +1.5). Almost all of that comes from defensive alignment, including putting the best pitch-framer behind the plate. At free-agent prices of $8-12M per win, that is roughly **$9-14M a season**. The most conservative reading, counting only catcher framing, is about +0.3 wins, or $3M. Rivals can copy the approach, so the edge is temporary. Over a three-season head start it is worth roughly $18-23M in present value, against about $3 a season in model costs. The starter-choice recommendations add about +0.2 wins on top. Because wins are zero-sum, the gain exists only while other clubs don't use the same approach."

## What it means

**The bottom line: the app is worth about +1.4 wins a season, not +2.4. The honest range is about +0.5 to +1.9.** The +2.4 was measured correctly on its own terms, but it graded the optimizer partly on its own yardstick and treated each game as if it had no effect on the next. Once each piece is valued by what held-out data says it is worth, about 60% of the claim survives. Even the most conservative reading is still positive: about half a win.

**Piece by piece:**

| Piece | Claimed | Verified | Why it moved |
|---|---|---|---|
| Starter ("move the next starter up a day") | +0.8 | **+0.2** | The biggest correction. A one-game comparison treats the moved-up start as free, but the start he takes is one a later game loses. Replaying every team's 2026 schedule, only 28-44% of the one-game value survives a season, and starter ratings come true at about 0.76 per rated run. What does survive is real: the best starters get a few more starts on normal 4-day rest, and 4 days of rest showed no measurable performance penalty. |
| Defense (fielding + framing) | +1.4 | **+1.1** | The fielding and framing ratings are well calibrated across 2026: fielding about 1.0 per rated run, framing about 0.7. But the plans used the best-framing catcher in 76% of games, more than any real catcher's workload, so the framing gain is cut to what a real workload sustains. This is the piece with the one open warning (below). |
| Lineup offense | +0.2 | **+0.1** | The season-stats lens over-states hitter differences: only 0.40 of a rated wOBA difference shows up later. Small either way. |
| **Total** | **+2.4** (+1.8 to +3.0) | **+1.4** (+0.5 to +1.9) | |

**What supports the claim:**
- Starter quality predicts real runs within a team (slope 0.76, and 0.70 on the August-September hold-out).
- The defense ratings predict 2026 defense across 1,325 player-positions (slope 1.01) and 56 catchers (0.71). The rating isn't biased for players who are part-time at a position or new to it.
- Starting on 4 days of rest showed no measurable penalty in 2026.

**What weakens it:**
- **Circularity.** 58% of the claim (defense) was scored with the exact ratings and weight the optimizer maximized. The starter used the same rating in both, too.
- **The direct check on these 150 plans doesn't confirm fielding.** Re-scored with what the players actually did after the game, the plans' defensive edge is about −0.5 wins (−1.4 to +0.4), and the total is about 0 to +1. That check is noisy, and it is biased against part-time fielders, who lose innings by fielding badly. But it is the only test of these exact plans, and it doesn't back the fielding piece. That is why the honest range runs down to +0.5.
- **Lineup offense can't be confirmed at game level.** The within-team slope of real runs on the lens's lineup value is −0.25 (−0.78 to +0.26). Single games are too noisy, and day-to-day lineup changes are small.
- **The starter gain is mostly reshuffling,** as shown above. Whatever remains depends on teams accepting a few more starts for their best pitchers, and innings limits and injury risk aren't priced here.
- **Rest days.** 18 plans played a flagged-for-rest regular whom the manager benched. If those rest days must be taken anyway, about 0.3 wins of the claim moves to another day.
- **The published interval (+1.8 to +3.0) only resampled games.** It held the lens fixed, so it couldn't show any of the above.

**Why the two dollar views differ so much.** At market prices, +1.4 wins is worth about $14M a season (about $5M at the +0.5 floor). Through playoff odds alone, it is worth about $1-2M a season for a typical team and about $2M for a bubble team. The market price of a win is what free-agent buyers pay, and it bakes in regular-season revenue, franchise value and the fact that teams buy wins in big blocks. The playoff view counts only one channel, at $30M per berth. The two are best read as a ceiling and a floor on the value of a win, not as a sum.

**One team vs the league.** Wins are zero-sum. The +1.4 is a first-mover number: one team using the app against 29 that manage as they do now. If every team adopted it, the edges would cancel and what's left is cost and time: about $3 of model calls per team-season against hours of staff prep. The methods (defense, framing, rotation use) are known to front offices, so a head start would likely fade fast, as Moneyball's did.

**What was not changed.** No app behavior changed, and no money was spent (all of this is existing data and the saved plans). Three corrections the checks point to would each change the app, so each needs the user's OK:
1. A season-aware starter rule.
2. A catcher-workload cap in the lineup optimizer.
3. Pricing part-time fielders more cautiously.

**Suggested report wording (Impact section):**

> "We tested whether the AI staff's game plans would have won more often than what real managers did, using only information available before each game. On 150 sampled 2026 games, the raw model comparison said +2.4 wins over a season. We then stress-tested that number: we re-scored it with data the model never saw, checked each input against real results, and replayed full seasons so that moving a starter up a day isn't counted as free. Our best estimate is about **+1.4 wins per 162 games**, with an honest range of roughly **+0.5 to +1.9**. Most of it comes from defensive alignment: putting the best available glove at each position and the best pitch-framer behind the plate.
>
> In dollars, for a single team that adopts this first, +1.4 wins is worth roughly **$11-17M a season** at free-agent prices of $8-12M per win (about $5M at the conservative end). Measured only through playoff odds, it is a few percentage points for a bubble team, worth about $1-4M a season. Because wins are zero-sum, this is a first-mover edge, likely to fade within a few seasons as rivals copy it. If every team used it, no one would gain wins; the lasting value would be faster, cheaper game preparation."

**Avoid:**
- "Worth 2.4 wins."
- Any "$20M+ a year" claim.
- Any claim that all 30 teams would win more.
- Presenting the market-price and playoff-odds dollars as additive.

## Sources for the dollar assumptions

- **Price of a win (about $8M per WAR):** FanGraphs, [The Linearity of Cost per Win](https://blogs.fangraphs.com/the-linearity-of-cost-per-win/), and Joe Posnanski, [FanGraphs Money](https://www.joeposnanski.com/p/fangraphs-money) ("$8 million or so per win").
- **2025 salaries per WAR (about $8.3M for hitters, $11.6M for pitchers):** informal fan count, [Brewer Fanatic](https://brewerfanatic.com/forums/topic/46519-how-much-for-a-war-2025-highest-paid-players-edition/).
- **Wins are worth most near contention (85-95 wins):** FanGraphs, [The Marginal Value of a Win](https://blogs.fangraphs.com/the-marginal-value-of-a-win) and [Playoff Formats and the Marginal Win](https://blogs.fangraphs.com/playoff-formats-and-the-marginal-win).
- **Diamond Dollars (the original win-value model):** [The Hardball Times](https://tht.fangraphs.com/diamond-dollars-the-economics-of-winning-in-baseball-part-1).
- **A playoff appearance worth 20-30% of local revenue (NPV):** Vince Gennaro, via [Perfect Game Foundation](https://www.perfectgamefound.org/welcome-vince-gennaro-guest-blogger/).
- **Arizona's 2023 World Series run worth an estimated $30-40M:** [Front Office Sports](https://frontofficesports.com/article/padres-mlb-postseason-run-team-future/).
- **Hosting a Wild Card series ($5-15M of direct team revenue):** [Crain's Detroit](https://prod.crainsdetroit.com/node/928626).
- **Postseason pool and how shares are split:** [CBS Sports](https://hoopshype.games.cbssports.com/mlb/news/mlb-postseason-shares-how-dodgers-split-46-47-million-after-winning-2024-world-series/).
- **Revenue sharing (48% of net local revenue pooled):** [CBS Sports](https://www.cbssports.com/mlb/news/mlb-lockout-three-reasons-why-the-players-union-wants-to-alter-baseballs-revenue-sharing-system).
- **The Moneyball edge faded fast:** Hakes, J. K. and Sauer, R. D. (2006), "An Economic Evaluation of the Moneyball Hypothesis", *Journal of Economic Perspectives* 20(3).

Several of these figures are dated or informal. They set the range of assumptions; none is a precise current price.
