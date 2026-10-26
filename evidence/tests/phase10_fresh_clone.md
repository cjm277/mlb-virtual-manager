# Phase 10: fresh-clone dry run

**Result: setup takes about 1 minute (53 seconds of machine time), well under the 10-minute rule. A first game plan takes about 1 more minute.**

On 2026-10-25 (Windows 11, Python 3.14.7, git 2.x), the repo was cloned from GitHub into a brand-new folder with `.env` one level above it, as the graders will set it up. Every step in `README.md` was followed exactly and timed by a script, `evidence/logs/phase10_dry_run/dryrun.ps1`. The pip cache was turned off so package downloads were timed as on a fresh machine. The copy of `.env` was deleted afterwards, and no key value appears in any log.

## The timed run (brand-new folder `%TEMP%\p10`)

| README step | Command | Time | Result |
|---|---|---|---|
| 1. Clone | `git clone https://github.com/cjm277/mlb-virtual-manager.git` | 4.7 s | 1,379 files |
| 2. API key | `.env` one folder above the clone; nothing to copy | 0 s | found by the app |
| 3. Virtual environment | `python -m venv .venv` | 3.8 s | ok |
| 3. Packages | `.venv/Scripts/python -m pip install -r requirements.txt` | 43.1 s | ok (no pip cache) |
| 4. Key check | `.venv/Scripts/python -m backend.config` | 0.1 s | "Loaded .env from `...\p10\.env`; PORTKEY_API_KEY: found (value hidden); Model: gpt-6-luna" |
| 5. Start the app | `.venv/Scripts/python app.py` | 1.2 s to answer | home page 200; `/api/teams` 30 teams; `/api/games` TOR vs BOS 26 games; `/api/health` key found |
| **Setup total** | | **about 53 s** | **ready to use** |
| First plan (README's command-line example) | `run_plan.py --team TOR --opp BOS --date 2027-05-03` | 67.6 s | approved, 0 fix rounds, $0.0180, 17 model calls; the Pitching Coach used the new `model_starter` tool |

The 53 seconds is machine time. A grader reading the README and typing the commands might take 3-5 minutes in all, still far inside 10.

## What the dry run caught, and the fix

**Run 1 failed at the clone** (`evidence/logs/phase10_dry_run/run1_deep_folder_failed.txt`). It was cloned into a very deep folder: the folder path alone was 164 characters. Some saved evidence logs have long names; the longest path inside the repo is 104 characters. Windows limits a full path to 260 characters by default, so git stopped with "Filename too long" and every later step failed.

- **Who it could affect:** only a grader cloning somewhere very deep. A normal folder such as `C:\Users\<name>\Downloads\` (about 45 characters) leaves plenty of room, as run 2 shows.
- **Fix (commit ad9b9ad):** `README.md` step 1 now says to clone into a short folder on Windows. If git reports "Filename too long", run `git config --global core.longpaths true` and clone again.
- **Fix verified:** the same 164-character deep folder, cloned with long paths on, checked out all 1,379 files cleanly in 4.6 s.

**A timing slip in the test script, not the app.** Run 2's first readiness check polled `http://localhost:8000/` with a 2-second timeout and never got through, so it reported a 302-second wait. From PowerShell, a `localhost` request tries IPv6 first and takes 2.1 s before falling back (measured), so every poll timed out. The API calls just after it, with a 10-second timeout, all succeeded. Re-measured against `127.0.0.1` (`appstart.ps1`), the app answers 1.2 s after `python app.py`. A browser handles `localhost` without the delay.

## Files

- `evidence/logs/phase10_dry_run/run2_short_folder.txt`: the full timed log of the successful run, including the re-measured start-up.
- `evidence/logs/phase10_dry_run/run1_deep_folder_failed.txt`: the failed deep-folder run.
- `evidence/logs/phase10_dry_run/dryrun.ps1`, `appstart.ps1`: the scripts that ran the README steps and timed them.
