## Interpretation

**Two measures, two answers.** Scaled by what held-out data says each input is worth, the shipped lineup model (Marcel + catcher cap) is worth **+1.71 wins per 162** (+1.45 to +1.99) for the lineup insight. The direct check scores the same lineups on what the players did after the game:
- **Raw:** about **−1.0**.
- **With each fielder's short 2026 stint regressed** the way hitters already are: about **−0.15 (−0.24 to −0.06)**.
- **Marcel without the cap:** +0.01 (−0.09 to +0.10).

**Is the direct check fair?** A placebo says mostly yes (`scripts/direct_check_placebo.py`). The real manager's previous-game lineup, scored against his actual lineup on 4,313 team-games, came out −0.46 on the direct check and −0.46 on pre-game numbers, with defense at about 0. So the check doesn't penalize a lineup just for not being the one used. Its raw fielding part, though, takes every short stint at face value. Short stints average −0.13 to −0.19 runs a game counted once each, and −0.03 to −0.07 weighted by innings, in 2025 as well as 2026 (`defense_caution.md`). Part of that is real, and part is a fielder being moved off a position after a bad start, which freezes a bad small sample. The regressed version is the fairer reading of fielding; the raw one is the harshest.

**What each change did (paired, same games):**
- **Marcel projection: kept, confirmed.** Direct offense +0.46 wins (+0.41 to +0.52); verified offense +0.69. Rest-of-season wOBA tracks the Marcel value at slope 0.58, against 0.40 before.
- **Catcher cap: kept, costs about 0.2 wins on both measures.** It replaces an assumed 60-90% framing cut with a real limit. Without it the optimizer had one catcher catch every game, which neither measure charges for because neither can see fatigue. As built it binds harder than needed (busiest catcher 65% vs real managers' 75%), because it stacks with the 6-straight-starts rest rule.
- **Cautious fielder pricing: tested, NOT kept.** Both variants lowered both measures: calibrated −0.10 verified and −0.06 direct (regressed); strict −0.24 and −0.03.
  - **Why the calibrated version backfired:** priced on 2025 outcomes, out-of-position fielders cost −0.012 runs a game, not the −0.026 the app already charges. So "calibrated" made the optimizer *more* willing to move players.
  - **Why strict didn't help either:** it removed the thin-record credit, but the deficit didn't close.
  - The fielding gap on the direct check isn't fixed by pricing pre-game experience differently. It comes from fielders whose 2026 stints at the position turned out short, and before the game nobody knows whose will be.
- **Possibly-hurt starts: not the explanation.**
  - The plans start a player who doesn't appear that day or the next game in about a third of games.
  - Dropping those games moves the direct check by only about 0.1-0.2 wins: −0.77 raw and −0.11 regressed for the shipped model; −0.75 and −0.11 on the 2,819 games no version flagged.
  - The verified estimate barely moves (+1.69).

**What to claim (lineup insight, against real 2026 managers):**
- **Model-based (verified):** about +1.7 wins per 162.
- **Realized, fielding regressed like hitting:** about break-even (−0.15; Marcel without the cap +0.01).
- **Realized, raw:** about −1.0, the harshest reading.
- The gap is information managers have and our data doesn't: who is healthy and in form, and who is really able to play a position this year. The model is a strong stats-only baseline. On realized results it matches real managers rather than beating them, and Marcel was the one change that moved realized results clearly in our favor.
- Present the range, not the top number.

**Not done (needs the user's OK):**
- Loosen the catcher cap so it doesn't stack with the rest rule (target about 75%, what real catchers sustained).
- The starter rule, as planned.
