## 5. What the numbers mean

**Cost is not what limits this app.** With the Phase 8 settings, a game plan costs about 1.7 cents. One team's full season is about $3 including chat edits, and all 30 MLB teams for a season is under $100. That is less than one club's spending on bats for a week. Even 10,000 staffs (minor leagues, college, high school) come to about $9,000 a year in model cost, under $1 per staff per season.

**What does limit it at scale:**
- **Peak load, not total spend.** Most games start around 7 PM, so plans get built in the same two hours. At 10,000 staffs that is about 6M tokens per minute, which needs a high OpenAI usage tier or a job queue. Most plans could also be built on a schedule in the early afternoon, before lineup cards are due. The app's current guards (two builds at once, a $2 daily cap) suit a class project; at scale they would become a per-user cap and a queue.
- **Data, not tokens.** Statcast pitch tracking covers MLB and Triple-A. College and high-school teams would need TrackMan, Synergy or GameChanger feeds. Those cost far more than the model, and the tools would return less detail.
- **Pricing.** At the course slide's price (output $1.20 per 1M, no cached-input discount), costs roughly double: about $160 for the 30-team season. Still small.

**Repeat views cost nothing.** When the same request is sent again, Portkey answers from its cache (one rerun: 17 of 17 calls cached, $0). The app also reopens an identical request made within 24 hours at no cost. A staff of ten coaches sharing one plan pays for chat edits only, which is why the "10,000 coaches" row is cheaper than "10,000 staffs".

## 6. The experiments

**1. Fewer agent hops: self-check before handing in (shipped).**
- *What it does:* each scout and coach now runs the same code checker on its own output before handing it in. A double-booked position or a pinch-runner who is already starting goes straight back to that agent as one more step in its own loop (at most one retry). Before, it cost a full Manager review, a fix round, and a second Manager review.
- *Cost:* 14% cheaper ($0.0193 → $0.0165), 16% fewer input tokens, and 14% faster (67 s → 57 s). Agent runs per plan fell from 9.7 to 8.0.
- *Quality got better, not worse:*
  - The Manager approved 88% of plans (was 69%).
  - Checker problems at the first full check fell from 1.19 per plan to 0. Every one was fixed inside the agent.
  - Fix rounds fell from 1.31 to 0.44 per plan, and no plan finished with an open problem (was 0.25 per plan).
  - Against the real games, nothing moved: 7.0 vs 6.9 of the real starting nine, the real starter picked in 14 of 16 games under both, and relievers 50% vs 54%, which is within noise.
- *Why it works:* the plan reaches the Manager already legal, so the Manager spends its review on baseball judgment instead of bookkeeping.

**2. Shorter tool outputs: compact matchups (built and tested, off by default).**
- *What it does:* the `matchups` tool repeated the pitcher's pitch mix on every batter's row. The compact version lists it once per batter side and keeps every number (a test proves the checker sees the same numbers).
- *Text saved:* matchup output fell 47% (40.7k → 21.8k characters per plan). The pitchers scout's first pass used 7% fewer input tokens and the pitching coach's 3% fewer.
- *Total cost went up:* $0.0174 vs $0.0165 for self-check alone.
  - The reason was more Manager-requested fix rounds (62% of plans vs 31%), not the compact data.
  - Those requests were about rest days and positions, not numbers: there were zero made-up-number flags, the same number of hitter plans, and the same backtest results.
  - The real saving is about 2% of a plan, which is smaller than the run-to-run noise in 16 runs.
- *Decision:* not shipped, because the measured-best setup is the one that ships. The switch `MVM_COMPACT_MATCHUPS=1` turns it on.

**3. Prompt caching (already built in; measured here).**
- Every agent's fixed instructions come first and the game-specific parts come last, so OpenAI can reuse the start of each request. About half of all input tokens (52%) are billed at the cached rate ($0.02 instead of $0.20 per 1M). Without that, the same plan would cost about $0.027 instead of $0.0165, so caching already saves about 38%.
- The Manager, Comms and Team Doctor get almost no cache hits. Their fixed prompt is under OpenAI's 1,024-token minimum for caching, and the rest of their input is plan text unique to each run. Padding prompts just to reach the minimum isn't worth it: these three agents are only 30% of the bill.

**What's left.** Most remaining fix rounds are now the Manager overruling the Bench Coach on rest days. The Bench Coach keeps a tired hitter in when he has a clear matchup edge, as designed; the Manager sometimes asks to rest him anyway. Giving the Manager the same rest-day rule would remove most of the remaining fix rounds (about 0.4 per plan). That would cut cost again and keep the Moneyball rest policy consistent.
