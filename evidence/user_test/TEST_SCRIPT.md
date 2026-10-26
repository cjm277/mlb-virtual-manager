# Phase 9 test script: by hand vs the app (about 30 minutes)

**The game:** Blue Jays @ Yankees, **March 25, 2027** (2027 Opening Day). It hasn't been played, so you and the app both work from the full 2026 season and nobody can peek at a result.

**Setup (2 minutes)**
- The app is running at http://localhost:8000 (restart with `.venv\Scripts\python app.py` if not).
- Open `user_test.md` (this folder) to write in as you go. Have a phone stopwatch ready.
- Screenshots: **Win + Shift + S**, saved to `evidence/user_test/screenshots/` as `U_01.png`, `U_02.png`, and so on.

## Step 1: by hand, the way a busy coach would (capped at 20 minutes)

Start the stopwatch. Using **Baseball Savant** (plus MLB.com only for the Jays' roster), produce:

1. **Their starter:** your guess at who the Yankees start, and a mini scouting report on him: three bullets (what he throws, what he's good at, how we attack him).
2. **Our lineup:** nine Blue Jays, a position for each (C, 1B, 2B, 3B, SS, LF, CF, RF, DH) and a batting order. Use players on the end-of-2026 roster.

Work the way a real coach on a deadline would. Go with your gut where you normally would, and don't build a spreadsheet model. **Stop at 20:00** even if you're not finished.

Then write in `user_test.md`:
- the time, or "stopped at 20:00" and how far you got;
- your lineup on one line, like `Springer DH, Guerrero 1B, ...`;
- your three scouting bullets;
- **the shortcuts you took**, honestly. For example: batting the big names high, not checking platoon splits, skipping defense, trusting a hot streak or a reputation, not knowing who the starter would be.

📷 **U_01:** your Savant screen mid-way through.

## Step 2: the app does the same job (about 3 minutes)

Restart the stopwatch when you open http://localhost:8000. Pick Toronto, then the Yankees, then 2027-03-25, and build the plan. **Stop the watch when the lineup card and the "Their pitchers" scouting tab are both on screen.** Write the time in `user_test.md`.

📷 **U_02:** the lineup card. 📷 **U_03:** the "Their pitchers" tab (starter and certainty meter).

Optional: click **Download packets** and note how long the whole thing took, packets included.

## Step 3: your quote (2 minutes)

In `user_test.md`, write one or two sentences in your own words comparing the two: speed, quality, what surprised you. That's the quote for the report.

## Then tell the vibe coder

It will:
- score your hand-built lineup against the app's with the app's own win model, on the same starter and the same data (`scripts/score_hand_lineup.py`);
- pull the app's logged build time and cost (`scripts/summarize_runs.py`);
- finish `user_test.md` with the before-and-after table.
