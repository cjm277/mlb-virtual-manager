## Interpretation

**The value metric.** On public data, the shipped lineup model (Marcel projection + catcher workload cap) is worth **+1.71 wins per 162 (+1.45 to +1.99)** for the lineup insight: who plays, where, and in what order. That is up from +1.45 for this morning's model, and it is measured on all 4,801 2026 team-games, not 150. The starter-choice piece adds +0.22 (from the 150-plan verification), for about **+1.9 wins** in all. At $8-12M per win on the free-agent market, the lineup insight alone is roughly $14-21M a season to a club that adopts it first.

**What each change did:**
- **Marcel projection: kept.** Pooling each player's 2026 numbers with his 2025 numbers before regressing toward league removes 1.23x the July-September hold-out error. Verified offense rises from +0.41 to +1.10 wins, and the gain also shows up in what players did after the game (+0.46). A second back year (2024, downloaded for this) added nothing measurable on the hold-out (0.741% vs 0.740% signal), so it was left out: every input has to earn its place.
- **Catcher workload cap: kept.** It costs about 0.2 verified wins against the uncapped model, which had one catcher catching every game. That plan isn't physically realistic, and its framing gain had to be cut by assumption. With the cap, no catcher exceeds 70% of games, inside what 2026 catchers actually sustained (75% max), so the framing gain is counted in full. The cap now also replaces the catchers' 6-straight-starts rest flag rather than stacking with it; that cleanup changes 82 of 4,801 lineups.
- **Cautious fielder pricing: tested, not kept.** Both variants lowered the verified wins (calibrated −0.10, strict −0.24). Priced on 2025 outcomes, out-of-position fielders cost only −0.012 runs a game, not the −0.026 the app already charges, so the "cautious" version actually moved players more.

**Where a club's private information would add value.** Scored on what players did after the game, the same lineups come out about even with the clubs' own choices: −0.15 with short fielding stints regressed, or −1.0 taking every short stint at face value. Every club's decisions used information no public dataset has, and that gap points to where a club's own data would add the most:
- **Health and availability.** In about a third of games the plan starts someone who didn't appear that day or the next game, a sign of unlisted knocks. Medical and availability reports would remove those picks.
- **In-season form and role.** Offense on public data realizes below its rating mainly through picks a club would know to avoid.
- **Who can really play a position this year.** Fielders with short 2026 stints at a position realized well below their multi-year ratings. A club's own defensive tracking and coaching reports would price these moves directly.

Feeding those into the same optimizer is the natural next step for a team that licenses the program.

**Methods notes:**
- The placebo (`scripts/direct_check_placebo.py`): each club's previous-game lineup scored against its actual lineup gives the same answer before and after the game (−0.46 both). So the after-the-game check is a fair measure of information, not a biased one.
- Short fielding stints read badly partly because a fielder who starts badly gets moved off the position (`defense_caution.md`). That is why the regressed form is the fairer one.
