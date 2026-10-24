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
- **Once you pick your team**, the whole app changes to **that club's colors** (`phase5_02`): the top bar, the hero, the step markers, the lineup card's header, table headings, and the exported PDFs and HTML. The fade takes about half a second. All 30 clubs have a primary and secondary color.
- **Why:** it is your dugout. A Blue Jays manager sees Blue Jays blue on every screen and every printout. This is the clearest signal that the tool works for one specific club, not a generic stats site.

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

## Editing: the human stays in charge

- Every plan arrives as a recommendation. The manager can change any batting slot, position, the starter, or a bullpen role, then press **Save edits & re-check**.
- The same code checker re-runs in about a second, with no AI involved and no cost. A mistake like two center fielders turns the banner amber with the exact problem (`phase5_07`). Fixing it turns the banner blue (`phase5_08`). Moved players go to the bench automatically, and planned substitutions that no longer make sense are dropped and listed.
- **Why:** coaches will not trust a tool that overrules them, and they should not trust one that lets them make an obvious error. This keeps both sides honest.

## Export: who needs to know what

**Download packets (ZIP)** produces `hitters/`, `pitchers/`, and `coaches/` folders. Each document comes as a team-colored HTML page and a printable PDF. Hitters get the lineup card, the report on the opposing pitchers, and their briefing, never the pitching plan or medical notes. That rule lives in code, not in a prompt. This replaces "send an email" with something a staff could hand out today.

## Small touches

- The *Moneyball* line on the landing page sets the tone: analytics in service of the game.
- Stats are always labeled with what they're built on ("2026 season through the day before the game", or "Full 2026 season" for 2027 games), so nobody mistakes a projection for a fact.
- Plain language everywhere. "Their pitchers" and "Their hitters" instead of jargon, and a one-sentence "why" on every recommendation.
