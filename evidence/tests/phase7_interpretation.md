## Interpretation

*Draft by the vibe coder from the numbers above; edit freely. `scripts/backtest.py` keeps this file when it regenerates the table.*

**What the staff gets right**
- **The starting pitcher:** our Pitching Coach is free to reorder the rotation, yet it picked the pitcher the real manager started in **7 of 8** games. Houston was the miss: we chose Peter Lambert, and the Astros started Miguel Ullola.
- **Their starter:** the scout called the opponent's starter correctly in **7 of 8** games. Every one of those calls carried the app's "85% likely" label, and 7 of 8 is 88%, so the stated confidence held up in practice.
- **The starting nine:** our plans shared **7.1 of 9** starters with the real lineup. That is close to how much real lineups change day to day: teams share **7.5 of 9** with their own previous game. When we match a player, we usually put him at the same position (75%).

**Where it differs, and why**
- **Rest days (now built in).** Most "misses" were stars the real manager **rested**: Aaron Judge, Freddie Freeman, Yordan Alvarez, Cal Raleigh. At the time, the app always started the best healthy player, because nothing told it "he has played 12 straight days." **We added a rest-day rule**, and its thresholds come from 2026 data (`phase7_rest_thresholds.md`). A rest day is suggested after **6 straight starts for catchers and 10 for everyone else**, longer than three out of four real runs. The Moneyball twist is that the staff **chooses which day**. It rests the player when his matchup is weak, so the day off costs little, and keeps him in when he has a clear edge. Re-run on the Yankees game: Cody Bellinger had 10 straight starts but a clear edge against Ryan Feltner (.364 expected xwOBA), so the staff kept him in and pushed his rest to a weaker matchup (`evidence/logs/phase7_rest_rule_run/`).
- **Batting order: a deliberate point of difference.** We match the real slot only **21%** of the time, while real teams keep **72%** of slots from one day to the next. On average our order is 1.6 slots off. This is by design, not a flaw. The app isn't trying to copy a manager's habits. It builds today's order from today's evidence (on-base ability at the top, power in the middle, platoon edges against this starter), while real managers mostly keep a familiar order. **We chose not to anchor the Bench Coach to the team's usual order**: the point of the tool is to offer the evidence-based alternative to traditional thinking, Moneyball-style, and leave the human free to take it or not.
- **Relievers.** **46%** of the relievers real managers used were in our plan for the situation the game became. Bullpen use depends on things a pre-game plan can't know (the score in the 6th, who warmed up), and our scenario lists name only 2–4 arms each. So this measures how often the plan's first choices got the ball, not whether the plan was wrong.

**What the backtest caught and fixed**
1. **Atlanta: the scout overrode a correct call.** The rotation model found no rested Phillies starter and flagged a likely bullpen game, which was right: Tim Mayza opened. The scout then named their **closer**, Jhoan Duran, as the starter anyway. A new checker rule now rejects a late-inning reliever with no starts as the opposing starter, and the scout is told to report a bullpen game and name the likely bulk pitcher. Re-run: it called a bullpen game, with low confidence and long reliever Grant Holman as the likely bulk arm (`evidence/logs/phase7_backtest_after_fixes/`).
2. **Mets: an over-cautious Pitching Coach.** Two relievers who had only pitched the day before ("limited") were marked "unavailable," and the real manager used both. The coach's instructions now keep limited relievers in real roles, with a caution note. Re-run: Senga became setup and Pintaro middle relief, and no reliever the real manager used was marked unavailable.

**Bottom line**
On the decisions with clear right answers (who starts, who's healthy, who the other team throws), the staff matches real managers about as often as real managers match their own previous day. Where it differs, two things are going on:
- **Missing context, now partly fixed:** rest days.
- **Deliberate, evidence-based disagreement:** batting order.

Its value is in the second kind. It doesn't replace the manager's instincts; it hands him a data-backed second opinion and makes him decide.
