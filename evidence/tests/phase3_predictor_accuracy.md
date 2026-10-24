# Phase 3 predictor accuracy

Run 2026-10-24 07:57 by `scripts/evaluate_predictors.py` over every 2026 regular-season game (2,429 games, 4,858 team-games). Each prediction uses only data from before that game; no LLM is involved, so this costs nothing to run.

## Starting pitcher (rotation predictor)

| Measure | Result |
|---|---|
| **Predicted starter actually started** | **75.5%** (3,666 of 4,858) |
| Actual starter was one of our top 2 on-turn pitchers | 87.3% |
| Benchmark: MLB's own listed probable starter was right | 99.9% (4,856 games with a listing) |
| Games where the actual starter had never started before that season (call-ups, openers; unpredictable from rotation order) | 7.8% |

By confidence label and month:

| Bucket | Accuracy | Team-games |
|---|---|---|
| confidence high | 82.6% | 3,526 |
| confidence low | 30.4% | 112 |
| confidence medium | 59.1% | 1,220 |
| month 2026-03 | 44.1% | 152 |
| month 2026-04 | 84.7% | 784 |
| month 2026-05 | 77.7% | 838 |
| month 2026-06 | 79.1% | 788 |
| month 2026-07 | 71.3% | 742 |
| month 2026-08 | 77.5% | 834 |
| month 2026-09 | 67.5% | 720 |

## Opponent lineup (lineup predictor)

| Measure | Result |
|---|---|
| Average predicted starters who actually started (out of 9) | **7.51** |
| Games with 8 or 9 of 9 right | 54.4% |
| Correct position, for players we got right | 81.0% |
| Exact batting-order slot, for players we got right | 49.7% |

Lineups scored: 4,858 team-games. Runtime 48s.
