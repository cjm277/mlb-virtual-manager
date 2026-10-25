# The win-model lineup: before and after

Generated 2026-10-24 22:02 by `scripts/win_impact.py compare`. The same 150 sampled games, rebuilt by the full staff after two changes, both set by 2026 data rather than judgment:

1. **The lineup is built by code from the win model** (`backend/engine/winmodel.py`). The nine players, their positions and the batting order are chosen to maximize expected runs against the predicted starter. The hitter and starter inputs are the ones that best predicted real 2026 results out of sample (`evidence/tests/value_model_search.md`): hitter xwoba regressed at 200 PA, his own platoon split, and starter woba allowed regressed at 400 batters faced. The Bench Coach uses that lineup and plans the bench and the moves.
2. **Rest days are priced.** A hitter past the streak threshold showed no same-day fatigue cost in 2026 (+0.0145 wOBA, range +0.0084 to +0.0205; `evidence/tests/lineup_params.md`), so resting him is a pure cost today. The model rests him only on a day when it costs at most 0.25 win-probability points.
3. **The matchup score is shrunk toward season quality.** Its pitch-type detail showed no predictive value (worth -0.06 of a point of season value, range -0.34 to 0.19), so the matchup score now keeps 0% of it. Hunt / beware stays in the hitter plans as scouting detail.

Both versions are scored against the real manager's lineup and starter for the same game, with everything else held fixed. Win probability edge per game; 95% ranges are bootstraps over the games.

## Season stats (original lens, independent of the optimizer)

| | Before (staff's own lineup) | After (win-model lineup) |
|---|---|---|
| **Lineup + starter** | +0.11 pts (-0.30 pts to +0.51 pts) | **+0.94 pts** (+0.54 pts to +1.33 pts) |
| Wins per 162 | +0.2 | **+1.5** (+0.9 to +2.2) |
| Lineup alone | -0.37 pts (-0.57 pts to -0.16 pts) | +0.39 pts (+0.22 pts to +0.58 pts) |
| Lineup alone, exactly as code built it | | +0.44 pts (+0.27 pts to +0.61 pts) |
| Games where our plan is better | | 66% |
| **Change, after minus before (paired)** | | **+0.83 pts** (+0.60 pts to +1.06 pts), +1.4 wins per 162 |

## Improved predictive lens (what the optimizer maximizes)

| | Before (staff's own lineup) | After (win-model lineup) |
|---|---|---|
| **Lineup + starter** | +0.41 pts (+0.12 pts to +0.69 pts) | **+1.19 pts** (+0.91 pts to +1.46 pts) |
| Wins per 162 | +0.7 | **+1.9** (+1.5 to +2.4) |
| Lineup alone | +0.01 pts (-0.13 pts to +0.15 pts) | +0.75 pts (+0.62 pts to +0.87 pts) |
| Lineup alone, exactly as code built it | | +0.81 pts (+0.70 pts to +0.91 pts) |
| Games where our plan is better | | 88% |
| **Change, after minus before (paired)** | | **+0.78 pts** (+0.64 pts to +0.92 pts), +1.3 wins per 162 |

## App's raw matchup engine (pitch-type detail)

| | Before (staff's own lineup) | After (win-model lineup) |
|---|---|---|
| **Lineup + starter** | +1.10 pts (+0.55 pts to +1.63 pts) | **+1.62 pts** (+1.03 pts to +2.18 pts) |
| Wins per 162 | +1.8 | **+2.6** (+1.7 to +3.5) |
| Lineup alone | +0.06 pts (-0.26 pts to +0.38 pts) | +0.50 pts (+0.21 pts to +0.77 pts) |
| Lineup alone, exactly as code built it | | +0.54 pts (+0.28 pts to +0.81 pts) |
| Games where our plan is better | | 69% |
| **Change, after minus before (paired)** | | **+0.51 pts** (+0.16 pts to +0.89 pts), +0.8 wins per 162 |

The staff used the model lineup exactly (same nine, positions and order) in 96% of games; the rest are mostly Manager-requested changes in the fix loop.

## Does the improved lens predict real games better?

Each lens applied to every 2026 game with the real lineups and starters (lower Brier and log loss are better; AUC 0.5 is a coin flip):

| Lens | Brier, all games | Log loss, all games | AUC, all games | Brier, Jul-Sep | AUC, Jul-Sep |
|---|---|---|---|---|---|
| 54% for every home team | 0.2493 | 0.6918 | 0.500 | 0.2490 | 0.500 |
| Original season-stats lens | 0.2464 | 0.6858 | 0.561 | 0.2449 | 0.576 |
| Improved lens (the optimizer's model) | 0.2461 | 0.6854 | 0.569 | 0.2447 | 0.588 |

## What it means

**The win-model lineup turns the lineup from a cost into a gain, and the plans now beat the managers' plans by the numbers.**
- *On the independent season-stats lens* (the optimizer doesn't maximize it), the full plan is worth **+0.94 win-probability points per game: about +1.5 wins per 162, with a 95% range of +0.9 to +2.2.** Before, it was +0.2 wins and the range included zero.
- *Paired, game by game on the same 150 games,* the change alone is worth +0.83 points per game (+0.60 to +1.06), about +1.4 wins a season. It favors the new plan in two out of three games.
- *The lineup alone* moved from −0.37 points to +0.39 points on this lens. The starter part didn't change: it is still the Pitching Coach's call.

**Why this is a real gain, not just the model grading itself:**
- *The headline uses different inputs from the optimizer.* The optimizer picks hitters on xwOBA with each hitter's own platoon split. The headline lens values them on wOBA with the league-wide split. Both describe player quality, so they aren't fully independent, but the gain isn't guaranteed by construction there. On the optimizer's own lens the gain is +1.9 wins, so the independent lens keeps most of it.
- *Every input earned its place on held-out data.* xwOBA, each player's own platoon split, and the starter's quality were chosen because they predicted July–September plate appearances best after fitting on April–June. The pitch-type matchup detail was dropped because it predicted nothing (−0.06, range −0.34 to +0.19).
- *The improved model predicts real games better than the original.* AUC is 0.569 vs 0.561 over the season and 0.588 vs 0.576 on July–September, and both beat the home-field baseline. Single games stay close to coin flips, which is why an edge of about 1 point per game adds up to more than a win over 162.
- *The staff followed the model.* It used the model lineup exactly in 96% of games; the rest were Manager-requested changes, the healthy conflict kept on purpose.

**What the model still can't see (where a human may know better):**
- *Defense.* The model values offense only, for our lineup and the manager's alike. Some of the gain may come from choosing bats over gloves; the model only plays players at positions they have started, which limits but doesn't remove this. Pricing defense (Outs Above Average and catcher framing are already in the database) is the next accuracy step.
- *Day-to-day injuries.* The data knows injured-list moves only. About a third of plans started someone who didn't play that day or the next, and the earlier analysis showed excluding them barely moves the result.
- *Rest days.* 2026 shows no same-day fatigue cost, so resting is priced as a pure cost today, capped at 0.25 points. Long-run benefits of rest, if any, are outside a one-game model.
- *Moving a starter up a day* still carries its rotation cost (see `win_impact.md`).

**The claim the numbers now support:** "In 150 real 2026 games, using only information available the day before, the AI staff's plans were about 1 win-probability point per game more likely to win than the real managers' plans. That's roughly +1.5 wins over 162 games (95% range +0.9 to +2.2), using a win model whose inputs were chosen because they predicted real results out of sample."
