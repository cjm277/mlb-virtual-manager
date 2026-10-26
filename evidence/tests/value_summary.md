# Value summary: the verified wins and what they are worth (for report section 7)

This file adds up the two measured pieces; it computes nothing new. Wins are per 162 games, measured on public 2026 data. Each piece is valued by what held-out data says its inputs are worth.

| Piece | Verified wins per 162 | 95% range | Source |
|---|---|---|---|
| Lineup insight: who plays, where, in what order (Marcel projection + catcher workload cap, all 4,801 2026 team-games) | **+1.71** | +1.45 to +1.99 | `value_at_scale.md`, headline table |
| Season-aware starter rule (at most 2 extra starts; every team's 2026 season replayed) | **+0.08** | -0.02 to +0.18 | `starter_rule.md` |
| **Total** | **+1.79 (about +1.8)** | | sum of the two |

**What it is worth to one club that adopts it first**, at the free-agent price of a win ($8-12M per win, `value_verification.md`, Check 6):

| | At $8M per win | At $10M | At $12M |
|---|---|---|---|
| Lineup insight (+1.71) | $13.7M | $17.1M | $20.5M |
| Total (+1.79) | $14.3M | $17.9M | $21.5M |

**Against its cost:** about $3.14 of model calls per team-season, including chat edits (`phase8_tokenomics.md`, section 2).

**How the numbers came to be** (`value_at_scale.md`, `projection_search.md`, `starter_rule.md`):
- The morning's lineup model was worth +1.45. The Marcel projection (each player's 2026 numbers pooled with his 2025) removed 1.23x as much hold-out error, and the lineup value rose to +1.93. The catcher workload cap (no catcher catches more than 7 of 10 games) brought it to +1.71.
- Two ideas were tested and dropped because they didn't add value: cautious pricing of part-time fielders (+1.61 and +1.47), and a 2024 back year for the projection (0.741% vs 0.740% hold-out signal).
- The starter rule's value grows with the cap (+0.24 at 4 extra starts, +0.37 uncapped). The cap was kept at 2 to stay near a normal workload, since injury risk can't be priced from this data.

**Caveats:**
- Wins are zero-sum, so this is a first-mover value. It shrinks as rivals copy the approach (`value_verification.md`, Check 6).
- Scored on what players did after each game, the same lineups come out about even with the clubs' own choices: -0.15 with short fielding stints regressed (`value_at_scale.md`). Clubs decide with information no public dataset holds (health, in-season form, who can really play a position this year). Feeding that private information into the same optimizer is where a club using the app would gain most.
