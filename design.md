# Design: how MLB Virtual Manager looks and why

Screenshots are in `evidence/screenshots/phase5_*.jpg`.

## The idea behind the look

> "Yale, economics and baseball. You're funny, Pete." (*Moneyball*, 2011)

The app is for a person who loves the game and trusts the numbers. It should feel like walking into a clubhouse office the morning of a game: the club's colors on the walls, a scoreboard ticking, a lineup card on the desk. It should not feel like a chatbot. Everything on screen is something a manager already knows how to read: a lineup card, a bullpen chart, a scouting report, a scoreboard.

## Layout

| Screen | What is on it | Why it works for a manager |
|---|---|---|
| **Landing / setup** (`phase5_01`, `02`, `03`) | A hero banner, then four numbered steps: your team, opponent, game (2027 schedule or 2026 season), notes. Below that, recent game plans. | The same order a manager thinks in: who am I, who are we playing, which day, anything special. The page scrolls to each next step by itself. Recent plans can be reopened without spending anything. |
| **Live build** (`phase5_04`, `05`) | The staff as a six-stage pipeline (Medical, Scouting, Coaches, Checker, Manager, Comms), one card per agent, and a dark "press box" feed of every tool call underneath. | You watch your staff work instead of staring at a spinner. Parallel work is visible: both scouts light up together, then both coaches. When the checker sends something back, the feed shows exactly what and to whom. |
| **Review and edit** (`phase5_06` to `11`) | A status banner, then tabs: Lineup card, Pitching plan, Their pitchers, Their hitters, Medical, Game plan & briefings, Run details. | The tabs follow how a staff splits the work. The things a manager changes most (the lineup, the starter, bullpen roles) are dropdowns right where they are read. |

## Colors: league first, then your club

- **Before a team is picked**, the app wears **MLB navy (#041E42) and red (#BF0D3E)** with a generic baseball mark. It is neutral ground. No official logos are used.
- **Once you pick your team**, the whole app changes to **that club's colors** (`phase5_02`, `phase5_16`). The fade takes about half a second. All 30 clubs have a primary and secondary color. The color reaches:
  - the top bar and footer, and a tinted page background;
  - the card borders and shadows, the active tab, and the scrollbars;
  - the step markers, buttons, and batting-slot circles;
  - the live feed's background, the lineup card, and the table headings;
  - the exported PDFs and HTML.
- **Readable on every club:** text on team colors switches between white and near-black based on how light the color is. The Brewers' gold buttons get dark text (`phase5_19`), and the Blue Jays' blue gets white.
- **Why:** it is your dugout. A Blue Jays manager sees Blue Jays blue on every screen and every printout. This is the clearest signal that the tool works for one specific club, not a generic stats site.

## Ballpark photos (`phase5_15` to `19`)

Logos are trademarked, so the app uses **photos of each club's home ballpark** instead:
- **Landing page:** before a team is picked, the banner is a faded **mosaic of all 30 ballparks** behind league navy.
- **After you pick a team:** the banner becomes **your ballpark** (for the Blue Jays, Rogers Centre under the lights at the 2016 Wild Card Game).
- **Game tiles:** each tile shows the park the game is played in (Fenway Park for road games at Boston).
- **Build and review screens:** both open with a wide banner of **that game's ballpark**.

Every photo is **freely licensed on Wikimedia Commons**: Creative Commons BY / BY-SA, or public domain. Each one shows its photographer, license, and source link, as those licenses require. `scripts/fetch_team_photos.py` picked them in four steps:
1. It takes each ballpark article's main photo.
2. If that photo isn't usable, it searches Commons for other free landscape photos.
3. Only then does it fall back to a city skyline. (All 30 ended up as ballparks.)
4. I reviewed a contact sheet and hand-picked three replacements: the automatic Citi Field pick was an anthem singer, Great American Ball Park's was a thin panorama, and Rogers Centre's was a grey exterior.

The photos are committed, about 200 KB each, so the app works offline. A test checks that all 30 have a free license and a credit.

## How each element reads

- **The scoreboard counter** (top right, every screen): model calls, tokens in, % cached, tokens out, cost, time, in yellow LED digits on black, like a ballpark scoreboard. It counts up live during a build. Cost is a first-class number, not a hidden setting, and the format makes it fun to watch rather than alarming.
- **Agent cards**: grey and faded while waiting; a team-colored border and a pulsing dot while working; a green edge and "DONE" when finished, with "done ×2" if the checker sent work back. Each card shows model calls, tool calls, and the last tool used, so you can see who is doing the heavy lifting.
- **The feed**: monospace and dark. Green for finished work, amber for refusals and fix rounds, red for checker problems. It reads like a log because it is one; the same events are saved to the audit trail.
- **The status banner** answers "can I send this?" at a glance:
  - **Green**: approved by the manager agent and passed the checker.
  - **Amber**: issues to fix, listed right in the banner with who owns each.
  - **Blue**: you edited it, and code re-checked it.
- **The lineup card** looks like the real thing: cream card stock, a team-color header with the opposing starter, numbered red circles for batting slots, and a "Why" column so every choice is explained. Rows you changed turn yellow until you save.
- **Chips**: red for an edge to the batter or a high threat, green for an edge to the pitcher or a low threat, amber for "limited / cleared with caution". Baseball people scan colors faster than numbers.

## The staff, drawn as people (`phase5_12`, `phase5_13`)

Each agent is a small animated person at a desk, dressed for the job **in your club's colors**. The caps, jerseys and pullovers use the theme colors, so the Blue Jays staff wears Blue Jays blue.

| Agent | Outfit and props | While working |
|---|---|---|
| Team Doctor | White lab coat over a team polo, stethoscope, clipboard with a red cross | Writes notes, nods |
| Scout (their pitchers) | Team cap and polo, sunglasses, a **radar gun** | Raises the gun; the readout flashes "97" |
| Scout (their hitters) | Visor, scouting notebook, stopwatch | Writes while the stopwatch ticks |
| Pitching Coach | Home jersey #34, cap, a baseball | Tosses the ball |
| Bench Coach | Road-grey "COACH" jersey, the lineup card and a pen | Fills in the card |
| Manager | Team pullover, cap, grey beard, coffee and a bag of seeds | Nods and gives signs |
| Clubhouse Comms | Headset, cardigan, team lanyard, tablet | Talks; sound waves pulse |
| Manager's Assistant (chat) | Quarter-zip, glasses, tablet with chat bubbles | Types; bubbles pop |

At rest everyone breathes and blinks. Waiting agents are greyed out. The **consistency checker is drawn as a laptop, not a person**, because it is code, not an AI, and the picture should say so. Animations switch off for people who set "reduce motion".

**Why:** a manager runs a staff of people. Seeing a scout raise a radar gun while the scouting report is written makes the multi-agent idea obvious without explanation, and it's simply more fun to watch than a spinner.

## Their starter: how sure are we, and how should each hitter attack him? (`phase5_20`)

- **A real percentage, not a vibe.** Next to the expected starter, a meter reads, for example, "85% likely to start or pitch the bulk innings," with the reason: "right 85% of the time in 3,526 similar 2026 predictions." The number comes from `scripts/calibrate_starter.py`, which replays the predictor on every 2026 game. It is set by code, never by the AI. For 2027 games the meter honestly drops to about 11-22%, because a starter projected months ahead is close to a coin flip among five. The app then suggests re-running the plan once the rotation is set. The lineup card header carries the same percentage.
- **A plan for every hitter.** "Your plan against [starter]" gives each of our hitters a pitch group to **hunt**, one to **beware**, and a one-to-two-sentence approach that cites the numbers ("Sit on breaking balls: you're at .427 against them, while he allows .305"). Code chooses hunt and beware from the matchup data, weighted by how often the pitcher throws each group. The scout writes the coaching language around them, and the checker verifies every number. Small samples are called out. Hitters get this table in their packet.

## Editing: the human stays in charge

- Every plan arrives as a recommendation. The manager can change any batting slot, position, the starter, or a bullpen role, then press **Save edits & re-check**.
- The same code checker re-runs in about a second, with no AI involved and no cost. A mistake like two center fielders turns the banner amber with the exact problem (`phase5_07`). Fixing it turns the banner blue (`phase5_08`). Moved players go to the bench automatically, and planned substitutions that no longer make sense are dropped and listed.
- **Why:** coaches will not trust a tool that overrules them, and they should not trust one that lets them make an obvious error. This keeps both sides honest.

### Or just say it: the chat assistant (`phase5_14`)

The **Ask your assistant coach** button (bottom right) opens a chat with the Manager's Assistant. A manager can type what they would say to a bench coach:
- "I don't like Clement in this matchup." The assistant finds the best available second baseman with the data tools, swaps him in with a one-sentence reason, and moves Clement to the bench.
- "Who closes if Varland is down?" or "Why is Springer batting 4th?" It answers without changing anything.
- "Add a note: hold the runner at first late." The note goes into the coaches' packet.

The assistant can change **exactly what the dropdowns can change, and nothing more**. Its change is applied to a copy of the plan and run through the same code checker. If it breaks a rule, the assistant gets one chance to correct itself; otherwise **nothing is saved** and the chat says why ("Santander is out per the Team Doctor"). Every reply shows what changed and a green "Saved: passed every rule check" or a red "Not saved". Chat is disabled while there are unsaved dropdown edits, so the two ways of editing never fight.

**Why:** dropdowns are precise; chat is how managers actually talk. Offering both lets the skipper think out loud while the code keeps the plan legal.

## Export: who needs to know what

**Download packets (ZIP)** produces `hitters/`, `pitchers/`, and `coaches/` folders. Each document comes as a team-colored HTML page and a printable PDF. Hitters get the lineup card, the report on the opposing pitchers, and their briefing, never the pitching plan or medical notes. That rule lives in code, not in a prompt. This replaces "send an email" with something a staff could hand out today.

## Small touches

- The *Moneyball* line on the landing page sets the tone: analytics in service of the game.
- Stats are always labeled with what they're built on ("2026 season through the day before the game", or "Full 2026 season" for 2027 games), so nobody mistakes a projection for a fact.
- Plain language everywhere. "Their pitchers" and "Their hitters" instead of jargon, and a one-sentence "why" on every recommendation.
