# Phase 12: final pre-submission check

Run 2026-10-26 00:19 on the submission commit **7bb2156**, cloned fresh from GitHub into a new folder with `.env` one level above it, following `README.md` exactly. Log: `evidence/logs/phase10_dry_run/run4_submission_commit_7bb2156.txt`.

| Check | Result |
|---|---|
| Setup: clone, venv, install with no pip cache, key check, start the app | **54.4 s** (the 10-minute rule passes easily) |
| Use the app: open, pick a game, build, dropdown edit, chat, download packets | **all steps passed**: approved plan from 7 staff; edit re-checked with 0 issues; ZIP of 31 files in `coaches/`, `hitters/`, `pitchers/` |
| Automated tests on the clean clone | **123 passed** |
| `report.html` and `slides.html` in the clone | present, and byte-for-byte identical to the copies reviewed (11 printed pages; 10 slides) |
| `.env` committed? | no; `.env.example` lists `PORTKEY_API_KEY=` with no value |
| `report.html` loads anything from the internet? | no: every screenshot is embedded |
| `slides.html` | 5 screenshots embedded, plus the inline diagram and chart; reveal.js loads from the jsDelivr CDN (5.1.0), as the assignment suggests |
| Repo public | `https://github.com/cjm277/mlb-virtual-manager` answers HTTP 200 |

This build came back in 8 s for $0 because Portkey served the identical requests from its cache. The uncached build of the same game earlier took 64.7 s and cost $0.018 (`phase10_fresh_clone.md`).
