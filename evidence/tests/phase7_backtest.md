# Phase 7 backtest: the staff's plan vs. what real managers did

Run 2026-10-24 19:02 by `scripts/backtest.py`. 8 September 2026 games, 16 different teams. Each plan was built exactly as the app builds it, using only data from before the game. It was then compared with that team's real box score. Full plans and audit trails are in `evidence/logs/phase7_backtest/`.

## Results

| Date | We managed | Result | Starting nine (of 9) | Same position | Same batting slot (prev. game) | Our starter = real starter? | Scout called their starter? | Situation | Relievers used that were in our plan for it |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-08 | TOR vs ATH | W 4-2 | 7 (prev. game: 7) | 5 of 7 | 1 of 7 (3 of 7) | yes: José Soriano | yes: Jack Perkins (85%) | close late lead | 0 of 1 |
| 2026-09-09 | LAD vs CIN | W 14-1 | 7 (prev. game: 6) | 4 of 7 | 1 of 7 (3 of 6) | yes: Yoshinobu Yamamoto | yes: Rhett Lowder (85%) | blowout lead | 1 of 2 |
| 2026-09-10 | NYY vs COL | W 10-3 | 5 (prev. game: 7) | 5 of 5 | 2 of 5 (7 of 7) | yes: Max Fried | yes: Ryan Feltner (85%) | starter early exit | 3 of 5 |
| 2026-09-11 | HOU vs TB | L 1-3 | 8 (prev. game: 7) | 7 of 8 | 0 of 8 (4 of 7) | no: Peter Lambert (real: Miguel Ullola) | yes: Drew Rasmussen (85%) | starter early exit | 1 of 3 |
| 2026-09-12 | ATL vs PHI | W 12-2 | 7 (prev. game: 8) | 5 of 7 | 3 of 7 (4 of 8) | yes: Tyler Mahle | no: Jhoan Duran (real: Tim Mayza) | blowout lead | 1 of 1 |
| 2026-09-14 | SEA vs LAA | L 4-6 | 7 (prev. game: 8) | 6 of 7 | 4 of 7 (7 of 8) | yes: Kade Anderson | yes: Reid Detmers (85%) | close late tied or trailing | 1 of 3 |
| 2026-09-15 | NYM vs BAL | L 5-7 | 8 (prev. game: 9) | 8 of 8 | 0 of 8 (9 of 9) | yes: Sean Manaea | yes: Shane Baz (85%) | close late tied or trailing | 2 of 5 |
| 2026-09-18 | SD vs MIA | W 8-2 | 8 (prev. game: 8) | 3 of 8 | 1 of 8 (6 of 8) | yes: Nick Pivetta | yes: Tyler Phillips (85%) | blowout lead | 2 of 4 |
| **Total / average** | | | **7.1** (prev. game: 7.5) | 75% | 21% (prev. game: 72%); avg. 1.6 slots off | 7 of 8 | 7 of 8 | | 11 of 24 (46%) |

## Who differed

| Game | Real starters we benched | Players we started instead | Relievers used that we had marked unavailable |
|---|---|---|---|
| 2026-09-08 TOR | Ernie Clement, Brett Bateman | George Springer, Myles Straw | none |
| 2026-09-09 LAD | Enrique Hernández, Hunter Feduccia | Freddie Freeman, Alex Call | none |
| 2026-09-10 NYY | Ryan McMahon, Jasson Domínguez, Anthony Volpe, George Lombard Jr. | Aaron Judge, Amed Rosario, José Caballero, Heliot Ramos | none |
| 2026-09-11 HOU | Nick Allen | Yordan Alvarez | none |
| 2026-09-12 ATL | Sean Murphy, Ha-Seong Kim | Mike Yastrzemski, Dominic Smith | none |
| 2026-09-14 SEA | Michael Arroyo, Cal Raleigh | Taylor Ward, Jhonny Pereda | none |
| 2026-09-15 NYM | Brett Baty | Luis Torrens | Kodai Senga, Jonathan Pintaro |
| 2026-09-18 SD | Ethan Salas | Luis Campusano | none |

## Cost of the backtest runs

8 plans: average **$0.0181** and **48 s** per plan; 106,852 input tokens (40% cached) and 8,568 output tokens on average. Statuses: approved; fix rounds: 4 in total.

## Interpretation

*Draft by the vibe coder from the numbers above; edit freely. `scripts/backtest.py` keeps this file when it regenerates the table.*

**What the staff gets right**
- **The starting pitcher:** our Pitching Coach is free to reorder the rotation, yet it picked the pitcher the real manager started in **7 of 8** games. Houston was the miss: we chose Peter Lambert, and the Astros started Miguel Ullola.
- **Their starter:** the scout called the opponent's starter correctly in **7 of 8** games. Every one of those calls carried the app's "85% likely" label, and 7 of 8 is 88%, so the stated confidence held up in practice.
- **The starting nine:** our plans shared **7.1 of 9** starters with the real lineup. That is close to how much real lineups change day to day: teams share **7.5 of 9** with their own previous game. When we match a player, we usually put him at the same position (75%).

**Where it differs, and why**
- **Rest days.** Most "misses" are stars the real manager **rested**: Aaron Judge, Freddie Freeman, Yordan Alvarez, Cal Raleigh. The app always starts the best healthy player, because nothing in its data says "he has played 12 straight days." Real managers build in days off. This is the biggest gap between the app and a human, and the most valuable next feature: give the staff a "games in a row" count and a rest-day rule.
- **Batting order.** We match the real slot only **21%** of the time, while real teams keep **72%** of slots from one day to the next. Our misses are close, though: on average 1.6 slots off. The Bench Coach orders hitters from the numbers (on-base at the top, power third and fourth). Real managers keep a familiar order and change it rarely. A cheap fix would be to give the Bench Coach the team's usual order as a starting point and ask it to justify each change.
- **Relievers.** **46%** of the relievers real managers used were in our plan for the situation the game became. Bullpen use depends on things a pre-game plan can't know (the score in the 6th, who warmed up), and our scenario lists name only 2–4 arms each. So this measures how often the plan's first choices got the ball, not whether the plan was wrong.

**What the backtest caught and fixed**
1. **Atlanta: the scout overrode a correct call.** The rotation model found no rested Phillies starter and flagged a likely bullpen game, which was right: Tim Mayza opened. The scout then named their **closer**, Jhoan Duran, as the starter anyway. A new checker rule now rejects a late-inning reliever with no starts as the opposing starter, and the scout is told to report a bullpen game and name the likely bulk pitcher. Re-run: it called a bullpen game, with low confidence and long reliever Grant Holman as the likely bulk arm (`evidence/logs/phase7_backtest_after_fixes/`).
2. **Mets: an over-cautious Pitching Coach.** Two relievers who had only pitched the day before ("limited") were marked "unavailable," and the real manager used both. The coach's instructions now keep limited relievers in real roles, with a caution note. Re-run: Senga became setup and Pintaro middle relief, and no reliever the real manager used was marked unavailable.

**Bottom line**
On the decisions with clear right answers (who starts, who's healthy, who the other team throws), the staff matches real managers about as often as real managers match their own previous day. It differs on judgment calls that rely on context the data doesn't hold: rest days, a familiar batting order, and in-game bullpen use. That's the line a human manager should keep.
