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
