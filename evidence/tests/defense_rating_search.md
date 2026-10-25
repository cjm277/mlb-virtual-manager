# Building a defensive rating that predicts next season

Targets: every fielder-position with 50+ innings (1,526) and catcher with 500+ pitches (113) in 2025 and 2026, predicted only from earlier seasons (2023 onward). "Skill explained" = 1 − weighted squared error / weighted squared rating (higher is better; 0 = no better than calling everyone average). Script: `scripts/defense_rating_search.py`.

| Rating | Seasons | Regress at | Skill explained | Correlation with next season |
|---|---|---|---|---|
| fielding | 3 seasons, 1 / 0.6 / 0.3 | 600 innings | 0.137 | 0.26 |
| fielding | 3 seasons, 1 / 0.8 / 0.6 | 600 innings | 0.136 | 0.26 |
| fielding | 3 seasons, equal | 600 innings | 0.133 | 0.26 |
| fielding | 3 seasons, 1 / 0.8 / 0.6 | 1,000 innings | 0.132 | 0.26 |
| fielding | 3 seasons, 1 / 0.6 / 0.3 | 1,000 innings | 0.131 | 0.26 |
| fielding | 3 seasons, equal | 1,000 innings | 0.131 | 0.26 |
| fielding (best using last season only) | last season only | 600 | 0.117 | 0.23 |
| framing | 3 seasons, 1 / 0.6 / 0.3 | 6,000 pitches | 0.296 | 0.52 |
| framing | 3 seasons, 1 / 0.6 / 0.3 | 12,000 pitches | 0.286 | 0.51 |
| framing | last season only | 6,000 pitches | 0.285 | 0.50 |
| framing | 3 seasons, 1 / 0.8 / 0.6 | 12,000 pitches | 0.281 | 0.51 |
| framing | 3 seasons, 1 / 0.8 / 0.6 | 6,000 pitches | 0.281 | 0.52 |
| framing | 3 seasons, equal | 12,000 pitches | 0.271 | 0.50 |
| framing (best using last season only) | last season only | 6,000 | 0.285 | 0.50 |

**Chosen:** seasons weighted [1.0, 0.6, 0.3], fielding regressed at 600 innings, framing at 6,000 pitches.

**Players with no history at a position** (what such fielders actually did there in 2025-2026, per 9 innings): new to the position but played elsewhere -0.0261 runs (32,042 innings); no MLB fielding history at all -0.0065 runs (66,413 innings). These replace "assume average" for unrated players.
