## Interpretation

**Two measures, two answers.** Scaled by what held-out data says each input is worth, the verified estimate rises from +1.45 to **+1.71 wins per 162** for the lineup insight (+1.94 with the starter piece). The direct check scores the same lineups on what the players did after the game, and on 4,801 games it comes out *negative*: about **−1.0 (−1.1 to −0.8)** for the shipped version. On 150 plans that check was too noisy to read. At 30 times the games it isn't noisy, so it can't be dismissed.

**Is the direct check fair? A placebo says yes, mostly** (`scripts/direct_check_placebo.py`, `evidence/logs/value_at_scale/placebo.json`). The real manager's *previous-game* lineup was scored against his actual lineup on 4,313 team-games. Both are the manager's own choices, so a biased check would penalize the unused one.
- Direct check: −0.46 (−0.60 to −0.31).
- Pre-game numbers: −0.46 (−0.53 to −0.39).
- Defense: −0.02 (−0.15 to +0.11).

So the check doesn't penalize a lineup just for not being the one that was used. Where the manager's choices are rated the same before and after the game, the two measures agree.

**What the improvements did (paired, same games):**
- **Marcel projection: confirmed.** Offense on the direct check improves by +0.46 wins (+0.41 to +0.52). The verified estimate says +0.69. Rest-of-season wOBA tracks the Marcel value at slope 0.58, against 0.40 for the old value. This is a real forecasting gain.
- **Catcher cap: costs about 0.2 wins on both measures** (direct −0.23, verified −0.22). It swaps an assumed 60-90% framing cut for a real constraint. In practice it binds harder than intended: the busiest catcher reaches 65% of games, while real managers' busiest reached 75%. That's because it stacks with the 6-straight-starts rest rule, which reads the real team's history.

**Where the direct-check deficit comes from:**
- **Defense** (`scripts/direct_check_defense_gap.py`): almost all of the fielding gap comes from fielders with **1-99 innings at that position in 2026**. The model plays about 0.6-0.75 more of them per game than the real manager, and their realized 2026 rates are far below their pre-game ratings. Those rates are small-sample and include players benched after a bad start, so they overstate the gap. But the model's distinctive defensive moves are exactly the ones real managers rarely made, so 2026 has almost no clean data to confirm them. If each fielder's 2026 rate is regressed toward his pre-game rating at 600 innings, fielding turns slightly positive, but that adjustment leans on the very ratings under test. Framing is positive on the direct check (smaller with the cap).
- **Offense**: the Marcel picks are rated about +1.9 wins on unscaled pre-game numbers, but realize about −0.1. The placebo shows that managers' own swaps realize as rated. So the model's picks carry something the stats miss, and managers know it. Likely causes are health, in-season form and role. In 32% of games the model started a player who didn't appear that day or the next game, a sign of unlisted minor injuries.

**What to claim:**
- The verified +1.7 is a model-based estimate. It assumes real managers know only what our data knows.
- The direct check says they know more, and on realized results the lineup insight alone does not beat them yet.
- The honest range for the lineup insight now runs from about −1 (direct) to +1.7 (verified). A value claim should present both, not the upper figure.

**Changes kept in the app:**
- The Marcel projection (confirmed on both measures).
- The catcher cap (realism; small cost).

**Next steps (not taken; they need the user's OK):**
1. Price fielders with little 2026 time at a position cautiously, in the optimizer itself (the earlier "part-time fielders" fix).
2. Re-run the direct check excluding possibly-hurt starts.
3. Loosen the cap so it doesn't stack with the rest rule.
4. The starter rule, as planned.
