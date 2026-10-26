# Phase 9: real user test

**User:** the developer (CM), a Blue Jays fan, not a coach. The rubric's Impact evidence is "a real user tried it (a quote, screenshot, or before-and-after time)". The user here is the person who built the app, and that is stated plainly.
**Session:** Sunday 2026-10-25, 22:57-23:02 local time, on the local app (http://localhost:8000).
**Game:** Toronto Blue Jays vs Tampa Bay Rays, **Monday July 20, 2026**, at Rogers Centre. This is a played game, so the staff used only stats from before that date, as if planning that morning. (`TEST_SCRIPT.md` suggested the 2027 opener; the user picked this game instead.)
**Run log:** `runs/2026-07-20_TOR-vs-TB_20261025-225719/` (`audit.jsonl`, `plan.json`, `chat.json`); times and costs from `scripts/summarize_runs.py runs --since 20261025-2250`.

## What the user did, step by step

| # | Step | What happened | Screenshot |
|---|---|---|---|
| 1 | Pick the team | Chose Toronto. The page switched to Blue Jays colors and the Rogers Centre photo. | `screenshots/U_01_pick_team.webp` |
| 2 | Pick the opponent | Chose Tampa Bay. The 2027 schedule (upcoming games) showed first. | `U_02_pick_opponent_2027_schedule.webp` |
| 3 | Pick the game and build | Switched to the 2026 season, picked July 20, and clicked "Build game plan" ("About 1 minute and 2 cents"). | `U_03_pick_2026_game_and_build.webp` |
| 4 | Watch the staff work | The Team Doctor started first, then the scouts and coaches in parallel. The live counter tracked model calls, tokens and cost. | `U_04_staff_building.webp` |
| 5 | Read the lineup card | Approved by the manager, and the checker passed the first time. Every player has a reason with numbers: runs per PA, defense, platoon edge, and rest-day calls priced in win probability (e.g. "resting [Guerrero] costs 1.42 win-probability points"). Kirk DHs "after catching 7 of the team's last 10 games". | `U_05_lineup_card.webp` |
| 6 | Read the pitching plan | "Rotation rule recommends Gausman; he is ready after 7 days rest." Five innings, a 90-pitch limit, a pitch mix by batter side, a bullpen role for every reliever, and six game scenarios. | `U_06_pitching_plan.webp` |
| 7 | Their starter and certainty | Expected starter Nick Martinez (RHP), **61% likely** ("right 61% of the time in 1,220 similar 2026 predictions"), with a hunt/beware plan for every Jays hitter. | `U_07_their_pitchers.webp` |
| 8 | Their hitters | The Rays' predicted lineup against a right-hander and against a left-hander, plus how to pitch each threat. | `U_08_their_hitters.webp` |
| 9 | Medical | Ten players out (injured list), four relievers limited by workload, four hitters with "rest suggested" after 13-19 straight starts. | `U_09_medical.webp` |
| 10 | Game plan and briefings | The manager's keys and decisions, and a separate briefing for hitters, pitchers and coaches. | `U_10_game_plan_and_briefings.webp` |
| 11-12 | Edit by chat | The user typed: *"Varsho seems to have something going on in his personal life, let's give him a rest day today."* The assistant benched Varsho, moved Myles Straw to center, dropped a planned move that involved Varsho, and re-checked the plan in code: "Saved: the plan passed every rule check." | `U_11_chat_request.webp`, `U_12_chat_edit_rechecked.webp` |

## The numbers (from the run log)

| | |
|---|---|
| Time to a full game plan (lineup, pitching plan, both scouting reports, medical, briefings) | **47 seconds** (46.9 s) |
| Model calls / input tokens (cached) / output tokens | 18 / 96,829 (43,471, 45%) / 7,856 |
| Cost of the plan | **$0.0155** |
| Chat edit (2 model calls) | $0.0012, applied and re-checked in seconds |
| Whole session, from clicking Build to the edited plan being saved | about **4.5 minutes** (22:57:19 to 23:01:48), most of it reading |
| Manager review | approved; the checker found 0 issues, 0 fix rounds |

## Before and after

| | By hand (public sites) | The app |
|---|---|---|
| Time | **pending: the user's by-hand time** | 47 s to build; about 4.5 min including reading and one edit |
| Output | **pending** | a full plan: lineup with reasons, pitching plan with bullpen scenarios, both scouting reports, medical, three role briefings, and downloadable packets |
| Cost | the coach's time | $0.017 including the chat edit |

## What the session showed

- **A first-time flow with no help.** Team, opponent, game and build took four clicks, and every screen was reached from the tabs.
- **The season-aware starter rule worked live, for the first time.** The Pitching Coach called `model_starter` and started its pick (Gausman, 7 days of rest). The plan text cites the rule.
- **Private information goes in through the chat.** The user's one edit was exactly the kind of thing no public dataset has: a player's personal situation. The assistant applied it in plain English, and code re-checked the whole plan before saving. This is the private-information route the value analysis points to (`value_at_scale.md`): a club adds what only it knows, and the model does the rest.
- **The plan explains itself in numbers.** Every lineup choice, rest call and pitching key cites a figure from the data, and the opposing-starter certainty comes with its own track record (61% on 1,220 similar predictions).

## In the user's words

> **pending: one or two sentences from the user**
