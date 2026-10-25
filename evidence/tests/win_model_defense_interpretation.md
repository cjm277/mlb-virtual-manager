## What it means

**Defense adds about another win and a third, and the plans now beat the managers' plans by about 2.4 wins a season.**
- On the season-stats lens, the full plan (lineup + starter, with defense on both sides) is worth **+1.47 win-probability points per game: +2.4 wins per 162, with a 95% range of +1.8 to +3.0.** It's better than the real manager's plan in 74% of games.
- Paired on the same games, the defense-aware lineup beats the offense-only one by **+0.77 points (+0.61 to +0.94), about +1.3 wins.** It beats the staff's original lineup by +1.37 points (+1.12 to +1.61), about +2.2 wins.
- **The lineup alone** went from −0.37 points (the staff's own judgment) to +0.14 (offense-only model) to **+0.96 (+0.78 to +1.17)** with defense.
- **Where the defensive gain comes from:** the v3 fielders save +0.11 runs per game, against +0.03 for the real managers' and 0.00 for the offense-only model. It puts the best glove at each premium position, the best framer behind the plate, and the weakest glove at DH. The offense-only model ignored the glove entirely, which is why it gave some of its gain back once defense was counted.
- On the optimizer's own lens the edge is +2.9 wins. The independent season-stats lens keeps most of it.

**Why each piece can be trusted:**
- **No look-ahead.** Defensive ratings use only seasons before the game (2023–2025 for 2026 games), and a test checks this.
- **The rating predicts the future.** The three-season, position-specific rating predicted the next season's defense better than one season alone (explains 0.137 vs 0.117 of next-season fielding; framing correlates 0.52 year to year).
- **Out-of-position players are priced from data, not assumed average.** Fielders new to a position actually cost −0.026 runs per game there.
- **A rated run is worth a real run.** On 2026 games, rated fielding moved runs allowed by −1.15 per run and framing by −1.31, both consistent with 1.

**A bug this run surfaced, now fixed.**
- **The bug:** since Phase 4, the stat checker read quoted numbers without their minus sign. A real stat like "−0.0038 runs per PA" didn't match the tool's −0.0038, so it was flagged as made up.
- **Why it showed up now:** the model lineup's per-player numbers are often negative, so the Manager kept sending correct lineups back. 30 of 150 plans ran out of fix rounds and ended as "needs human review".
- **Why the result still stands:** with the fix, re-checking those plans clears every flag, and the lineups themselves were unaffected. The staff used the model lineup exactly in 142 of 150 plans, and the others differ by 0–2 players.
- **Smaller fix:** a tired player with no legal replacement is now described as such, instead of "costs 100 points".

**What the model still can't see:**
- Outfield arm strength (Outs Above Average doesn't include throwing), catcher blocking and throwing, and baserunning.
- Day-to-day injuries.
- The rotation cost of moving a starter up a day.

These are the next candidates. Each would need to earn its place the same way.

**The claim the numbers now support:** "Across 150 real 2026 games, using only information available the day before, the AI staff's plans were about 1.5 win-probability points per game more likely to win than the real managers' plans, counting both offense and defense. That's roughly +2.4 wins over a 162-game season (95% range +1.8 to +3.0), from a model whose every input was chosen because it predicted real results."
