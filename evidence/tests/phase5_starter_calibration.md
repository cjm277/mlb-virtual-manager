# Starting-pitcher prediction: how sure are we?

Run 2026-10-24 13:45 by `scripts/calibrate_starter.py` over every 2026 game. A prediction counts as **right if that pitcher started, or pitched the bulk innings after an opener**. The app shows these rates as the percentage next to every predicted starter.

## 2026 games (live predictor)

| Confidence label | Right | Predictions |
|---|---|---|
| all | 78.2% | 4,858 |
| high | 85.4% | 3,526 |
| low | 35.7% | 112 |
| low (early season) | 33.3% | 3 |
| medium | 61.2% | 1,220 |
| medium (early season) | 45.0% | 149 |

## 2027 games (preseason projection, measured on 2026)

The 2027 starter is a projection made before the season: Opening Day roster, ranked by the prior season's starts, cycled through the schedule. Doing exactly that for 2026 and checking it against what happened:

| Games into the season | Right | Predictions |
|---|---|---|
| 1-10 | 22.3% | 300 |
| 11-25 | 18.7% | 450 |
| 26-50 | 14.5% | 750 |
| 51-100 | 18.2% | 1,500 |
| 101-162 | 10.9% | 1,858 |
| all | 15.2% | 4,858 |

Runtime 29s.
