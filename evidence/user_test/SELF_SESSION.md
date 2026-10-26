# Phase 9: your own real-user session (about 25 minutes)

You're the user: a baseball fan preparing a game the way a coach would. Use the app as you would for real. Don't fix anything mid-session; anything that annoys or confuses you is evidence. The app logs every build's time, tokens and cost on its own. You record the three things the rubric names: **screenshots, times, and your own words**.

## Before you start (2 minutes)

1. Check the app is running at http://localhost:8000 (the "MLB Virtual Manager" terminal tab). Restart it if needed: `.venv\Scripts\python app.py`.
2. Open `sessions/CM.md` beside the app. Write the **start time** at the top; the run summary uses it to pick out your session's plans.
3. Have a timer ready (phone stopwatch). Screenshot with **Win + Shift + S** and save into `evidence/user_test/screenshots/` as `CM_01.png`, `CM_02.png`, and so on, one per 📷 below.

## Part A: the "before" time (10 minutes max, optional but the strongest evidence)

Pick one real 2026 game, for example a Jays game you remember. **Without the app**, using only public sites (Baseball Savant, FanGraphs, MLB.com), try to:

1. pick a starting nine and a batting order for that game, against that day's opposing starter;
2. write a two-line scouting note on the opposing starter.

**Stop at 10 minutes** whether or not you're done. Record how long it took, or how far you got by 10 minutes. That is the "before" time. A real staff does this for every game, plus the bullpen plan and the packets.

## Part B: the same job with the app (about 10 minutes)

Use **the same game** as Part A. Start the stopwatch at task 1 and note the clock time at each task in `sessions/CM.md`.

| # | Task | 📷 |
|---|---|---|
| 1 | Pick your team, the opponent and the game. | CM_01: the game picker with your choice |
| 2 | Build the plan. Watch the staff work. | CM_02: the staff mid-build (agent figures working) |
| 3 | Read the lineup card. Would you play these nine in this order? Pick one player and judge his reason. | CM_03: the lineup card |
| 4 | Find the opposing starter and how sure the staff is. | CM_04: the "Their pitchers" tab with the certainty meter |
| 5 | Look at the pitching plan: our starter, and who comes in if it's close late. | CM_05: our pitching plan |
| 6 | Change something with the dropdowns (swap two players or a position). | CM_06: the edit and the checker's result |
| 7 | Change something by chatting with the assistant coach, in your own words. | CM_07: the chat exchange |
| 8 | Download the packets and open one file. | CM_08: an opened packet |

## Part C: a second game (3 minutes, optional)

Build a plan for a different game, ideally a 2027 one, and time it from first click to finished plan. Was it faster the second time? 📷 CM_09: the finished plan.

## Afterwards (3 minutes)

1. Fill in `feedback_form.md` as yourself and save it as `sessions/CM_feedback.md`. The "in your own words" answers are your quotes, so write them as you'd say them.
2. Tell the vibe coder you're done. It will run `.venv\Scripts\python scripts\summarize_runs.py runs --since <your start time>` for the logged build times and costs, and turn everything into `phase9_user_test.md`.

**Be honest in the notes.** The report will say plainly that the user was the developer, a baseball fan rather than a club's staff. An honest list of what was clunky is worth more to the grade than praise.
