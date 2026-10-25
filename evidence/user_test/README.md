# Phase 9: real user test

Goal: a real person uses the app the way a coach would, and we record what happened. That means at least one quote, screenshots, and ease-of-use notes. Testers only *use* the app; there is no hand-built comparison plan.

## Before each session (2 minutes)

1. Start the app: `.venv\Scripts\python app.py`. It opens http://localhost:8000.
2. The tester sits at your computer, or watches your screen share and tells you what to click. The app runs on your machine, so it isn't reachable from theirs.
3. Open `session_notes_template.md`, copy it to `sessions/<initials>.md`, and keep it open beside the app.
4. Give the tester `TESTER_GUIDE.md`, or read the tasks out loud. Don't explain the app first; how far they get on their own *is* the ease-of-use evidence.

## During the session (10-15 minutes)

- **Stay quiet unless they're stuck for more than a minute.** Note where they got stuck and what you said.
- **Write down anything they say out loud, word for word.** That's where the best quotes come from.
- **Take a screenshot (Win + Shift + S) at each camera mark in the tester guide.** Save them to `screenshots/` as `<initials>_01.png`, `<initials>_02.png`, and so on.
- **Each plan costs about 2 cents and takes about a minute.** The app's $2-a-day cap allows about 100 builds.

## After the session (3 minutes)

1. Have them fill in `feedback_form.md`: the ratings, then one or two sentences in their own words. Ask whether you may quote them, and how they'd like to be named.
2. Save the form as `sessions/<initials>_feedback.md`.
3. Optional: run `.venv\Scripts\python scripts\summarize_runs.py runs` for the time and cost of the plans they built.

## Who counts

Any real person who isn't building the app: friends (a baseball fan or someone who has coached is ideal), family, or a classmate. One good session is enough for the assignment; two or three make the report stronger. Your own use doesn't count as a tester session, but your notes are still useful context.

When the sessions are done, tell the vibe coder. It will turn the notes, forms and screenshots into `evidence/user_test/phase9_user_test.md`, a summary with the quotes, the ratings, what was confusing, and any fixes made because of it.
