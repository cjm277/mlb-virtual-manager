# Phase 8 tokenomics: what a game plan costs, at every scale

Generated 2026-10-24 20:17 by `scripts/tokenomics.py` from real token counts in the audit trail of every run (input, cached input and output tokens are logged for each model call).

**Pricing.** gpt-6-luna list price: **$0.20 per 1M input tokens, $0.02 per 1M cached input tokens, $0.50 per 1M output tokens** (genai-prices "GPT-6 Luna", checked against OpenAI's pricing page on 2026-10-12). The course's lecture slide prices a different model (gpt-5.6-luna) at $0.20 in / $1.20 out with no cached rate; that is shown as a worst-case sensitivity line. Model cost only: hosting and data are discussed separately.

## 1. Real token counts

**26 real game plans** built through the app and the command line between Phases 4 and 7 (`runs/`), plus the 48 Phase 8 experiment runs below. Fresh builds only: 4 rerun(s) that Portkey answered partly or wholly from its cache are counted separately.

| Per game plan | Mean | Median | 90th pct. | Cheapest | Most expensive |
|---|---|---|---|---|---|
| Cost (list price) | **$0.0190** | $0.0184 | $0.0245 | $0.0132 | $0.0270 |

Average plan: **116,356 input tokens (42% cached), 8,998 output tokens, 22 model calls, 62 s.** Input is about 76% of the bill even though output costs 2.5x more per token: each agent re-reads its instructions and every tool result on each step of its loop. A chat edit costs **$0.0010** per message (4 real messages). Lecture-slide pricing would make the average plan $0.0341.

Where the money goes (fresh production runs):

| Agent | Cost per plan | Share |
|---|---|---|
| bench coach | $0.0045 | 24% |
| pitching coach | $0.0033 | 17% |
| scout pitchers | $0.0030 | 16% |
| manager | $0.0028 | 15% |
| scout hitters | $0.0026 | 14% |
| clubhouse comms | $0.0016 | 9% |
| team doctor | $0.0012 | 6% |

Fix rounds are the biggest swing factor: 58% of plans needed at least one, and those plans cost $0.0218 on average vs $0.0151 for plans approved on the first pass.

## 2. Cost at scale

Using the shipped configuration's measured average of **$0.0165 per plan** (condition B below, the settings the app now ships with) and $0.0010 per chat edit. "Plan + 3 chat edits" assumes the manager makes three chat changes per game.

| Scope | Plan only | Plan + 3 chat edits |
|---|---|---|
| One game plan | $0.0165 | $0.0194 |
| One team, one month (26 games) | $0.428 | $0.503 |
| One team, full season (162 games) | $2.67 | $3.14 |
| All 30 MLB teams, one month | $12.84 | $15.10 |
| All 30 MLB teams, full season (4,860 team-games) | $80.00 | $94.11 |

At the slide's worst-case pricing, the full 30-team season would be $162.28 for plans only. For comparison, Yale gives each student $40 of tokens.

## 3. The 100 and 10,000 users question

A "user" here is one coaching staff that builds a plan before each of its games (1.2 plans per game, allowing for a rebuild when the lineup or starter changes) and makes 3 chat edits. Season lengths: Triple-A/Double-A about 150 games, college and high school about 40 on average.

| Who the users are | Plans per season | Model cost per season | Per user per season | Busiest hour (7 PM starts) |
|---|---|---|---|---|
| 100 users: every MLB staff plus 70 Triple-A / Double-A clubs | 18,000 | $339.85 | $3.40 | ~30 plans/hour = 10 model calls and 0.06M tokens per minute |
| 10,000 users: affiliated minors (120), NCAA D1-D3 (~1,000), NAIA/JUCO (~700), high-school varsity (~8,200) | 480,000 | $9,062.68 | $0.906 | ~3,000 plans/hour = 1,000 model calls and 5.96M tokens per minute |
| 10,000 users as individual coaches (about 10 per MLB/MiLB staff on 1,000 staffs) who share one plan per game | 168,000 | $5,474.59 | $0.547 | ~300 plans/hour = 0.60M tokens per minute, plus chat |

## 4. Cost-cutting experiments, before and after

Same 8 September 2026 backtest games (16 teams) for every condition, each game run twice, all three conditions run side by side at the same time against the same API. Portkey's cache was bypassed so every run was a real, billed run. Quality is measured by the code checker (did the plan pass first time, was anything left open, any made-up numbers) and the Manager (fix rounds). Agreement with what real managers did is shown only as a reference that a cost cut did not change the staff's thinking: matching real managers is not the goal, since the app is meant to offer evidence-based alternatives to traditional thinking.

| | A. Before (Phase 7 app) | B. + Self-check (fewer hops) | C. + Self-check + compact matchups |
|---|---|---|---|
| Runs | 16 | 16 | 16 |
| **Cost** |  |  |  |
| Cost per plan (mean) | **$0.0193** | **$0.0165** (-14%) | **$0.0174** (-10%) |
| Cost per plan (median / 90th pct.) | $0.0211 / $0.0233 | $0.0151 / $0.0219 | $0.0170 / $0.0245 |
| Input tokens (cached share) | 130,941 (51%) | 109,728 (-16%) (52%) | 119,226 (-9%) (54%) |
| Output tokens | 10,328 | 9,538 (-8%) | 10,424 (+1%) |
| Tool output characters (matchups) | 99,497 (40,713) | 87,117 (34,424) | 75,660 (21,764) |
| Model calls | 22.7 | 19.6 | 21.6 |
| Agent hops (agent runs per plan) | 9.7 | 8.0 | 8.6 |
| Time per plan | 67 s | 57 s (-14%) | 63 s (-5%) |
| **Quality: process** |  |  |  |
| Approved by the Manager | 69% | 88% | 94% |
| Plans needing a fix round | 75% | 31% | 62% |
| Fix rounds per plan | 1.31 | 0.44 | 0.75 |
| Checker issues at first full check | 1.19 | 0.00 | 0.06 |
| Self-check catches (fixed inside the agent) | 0.00 | 0.38 | 0.94 |
| Open issues at the end | 0.25 | 0.00 | 0.06 |
| Made-up-number flags | 0.00 | 0.00 | 0.00 |
| Hitter plans written | 13.0 | 13.8 | 13.9 |
| **Agreement with real managers (reference only, not a target)** |  |  |  |
| Starting nine that really started | 6.9 of 9 | 7.0 of 9 | 6.9 of 9 |
| ...at the same position | 75% | 71% | 76% |
| Our starter = real starter | 14 of 16 | 14 of 16 | 14 of 16 |
| Scout called their starter | 14 of 16 | 14 of 16 | 14 of 16 |
| Relievers used that were in our plan | 54% | 50% | 52% |

Per-run detail is in `evidence/logs/phase8_tokenomics/results.json`; every run's plan and audit trail is saved beside it.

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
  - The staff's choices didn't shift: agreement with what real managers did stayed flat (7.0 vs 6.9 of the real starting nine, the same starter in 14 of 16 games, relievers 50% vs 54%, within noise). This is only a check that the cost cut didn't change how the staff thinks. Matching real managers is not the goal; the app is built to offer evidence-based alternatives to traditional thinking.
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

**What's left, and kept on purpose.** Most remaining fix rounds are the Manager overruling the Bench Coach on rest days. The Bench Coach keeps a tired hitter in when he has a clear matchup edge; the Manager sometimes asks to rest him anyway. That disagreement is deliberate: managers and bench coaches argue about exactly this, and the review step exists to surface it. It costs about 0.4 extra fix rounds per plan, a fraction of a cent, and is not engineered away.
