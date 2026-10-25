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
