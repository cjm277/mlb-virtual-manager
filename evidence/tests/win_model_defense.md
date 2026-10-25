# Offense and defense: the win-model lineup with defense built in

Generated 2026-10-24 23:00 by `scripts/win_impact.py defense`. The same 150 sampled games, three versions of the staff's plan, each scored against the real manager's lineup and starter with everything else held fixed. Both lenses now count defense on both sides: each fielder's runs saved at the position he plays, and the catcher's framing.

## How defense was added (all from data)

- **New data:** Outs Above Average and fielding runs prevented *at each position* (Savant, one leaderboard per position), innings at each position (MLB Stats API), and catcher framing, for 2023-2026 (`scripts/fetch_defense.py`). A game only uses seasons before it, so nothing leaks from the future.
- **The rating** weights the last three seasons [1.0, 0.6, 0.3] and regresses at 600 innings (framing at 6,000 pitches), chosen because it best predicted the next season's defense. Players with no history at a position get what such players actually did: -0.026 runs per game if they have played elsewhere (out of position), -0.007 with no MLB history (`evidence/tests/defense_rating_search.md`).
- **Its weight** was measured on every 2026 team-game: a rated run of fielding moved runs allowed by -1.15 (-2.24 to +0.06), and of framing by -1.31 (-2.39 to -0.18). Both ranges include −1, so a rated run counts as one run (`evidence/tests/defense_params.md`).
- **The optimizer** now values each player at each position as his runs scored plus his runs saved there, so the weakest glove tends to DH and the best catcher-framer catches.

Defensive runs saved per game by our fielders: real managers +0.026, v1 +0.025, v2 +0.001, **v3 +0.109**.

## Season stats + defense (independent of the optimizer's hitting inputs)

| Edge vs the real manager | v1: staff's own lineup | v2: model lineup, offense only | **v3: offense + defense** |
|---|---|---|---|
| **Lineup + starter, per game** | +0.11 pts | +0.70 pts | **+1.47 pts** |
| 95% range | -0.34 pts to +0.54 pts | +0.24 pts to +1.13 pts | +1.10 pts to +1.86 pts |
| **Wins per 162** | +0.2 | +1.1 | **+2.4** (+1.8 to +3.0) |
| Lineup alone | -0.37 pts | +0.14 pts | +0.96 pts (+0.78 pts to +1.17 pts) |
| Games where our plan is better | 44% | 59% | 74% |

Paired, same games: v3 minus v1 **+1.37 pts** (+1.12 pts to +1.61 pts), +2.2 wins; v3 minus v2 **+0.77 pts** (+0.61 pts to +0.94 pts), +1.3 wins.

## Improved lens + defense (what the v3 optimizer maximizes)

| Edge vs the real manager | v1: staff's own lineup | v2: model lineup, offense only | **v3: offense + defense** |
|---|---|---|---|
| **Lineup + starter, per game** | +0.41 pts | +0.94 pts | **+1.80 pts** |
| 95% range | +0.10 pts to +0.70 pts | +0.62 pts to +1.26 pts | +1.52 pts to +2.07 pts |
| **Wins per 162** | +0.7 | +1.5 | **+2.9** (+2.5 to +3.4) |
| Lineup alone | +0.01 pts | +0.51 pts | +1.41 pts (+1.24 pts to +1.58 pts) |
| Games where our plan is better | 54% | 68% | 89% |

Paired, same games: v3 minus v1 **+1.39 pts** (+1.22 pts to +1.54 pts), +2.2 wins; v3 minus v2 **+0.85 pts** (+0.73 pts to +0.99 pts), +1.4 wins.

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
