# Phase 9: real user test

The rubric's Impact evidence is "a real user tried it (a quote, screenshot, or before-and-after time)". It doesn't exclude the person who built the app, so the main test is the developer's own, run as a timed before-and-after:

1. **`TEST_SCRIPT.md`:** the script (about 30 minutes).
   - Build a mini scouting report and a lineup by hand from Baseball Savant, capped at 20 minutes.
   - Have the app do the same job for the same game, timed.
   - Write a quote; take screenshots.
2. **`user_test.md`:** the evidence file. The user fills in the top half during the session. The vibe coder then adds the before-and-after table, the app's logged time and cost (`scripts/summarize_runs.py runs --since <start>`), and a quality comparison: the hand-built lineup scored by the app's own win model (`scripts/score_hand_lineup.py`).

The report states plainly that the user was the developer, a baseball fan rather than a club's staff.

## Optional: extra testers

More sessions with other people (a friend who coaches, a classmate) would make the evidence stronger but aren't needed:
- give them `TESTER_GUIDE.md` and don't explain the app first;
- take notes in a copy of `session_notes_template.md` saved under `sessions/`;
- have them fill in `feedback_form.md` afterwards.

Each plan costs about 2 cents and takes about a minute; the app's $2-a-day cap allows about 100 builds.
