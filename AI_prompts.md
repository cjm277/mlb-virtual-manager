# AI Prompts

This file logs the prompts typed into the vibe coder while building MLB Virtual Manager. Secrets and API key values are never recorded.

Each phase section includes the phase name, the prompt typed, any follow-up prompts, and one sentence on what the first prompt was missing.

## Phase 1 - Scaffold and prompt log

- Prompt typed: "Alright let's get her started here with Phase 1: Scaffold and prompt log * Elements we need: * Make `Final Project/` the repo root, with a `.venv` and `requirements.txt`. * `.gitignore` excludes `.env`, `.venv`, raw data, and `node_modules`. * `.env.example` lists `PORTKEY_API_KEY` with no value. * A config loader looks for `.env` in the repo first, then the folder above. * Create `AI_prompts.md`, an `evidence/` folder for screenshots and logs, and a skeleton `README.md`. * Make the first commit and push to GitHub, either public or private with `zlisto` as a collaborator. * Evidence: a repo link that exists from day one. One note: do we really need an AI prompts log? When I read the project instructions, it doesn't seem like a requirement but let me know. Let's start with this and then let me know if there's anything you need from me before we move on to phase 2"
- Follow-up prompt: Answered the vibe coder's question: make the repo "Public" and name it "mlb-virtual-manager".
- What was lacking after the first: The prompt left the repo's visibility (public, or private with `zlisto`) and its name open.

## Phase 2 - Data pipeline

- Prompt typed: "Sweet. Let's keep this train rolling down the tracks Phase 2: Data pipeline Key elements: * Our move here should cover: a scripts/build_dataset.py that pulls: * all 30 teams; * the full 2026 schedule with probable pitchers; * the active roster for every team on every game date; * every 2026 box score; * 2026 Statcast pitch data by day, rolled up per player per game; * 2025 season totals for the fade; * sprint speed, fielding range (Outs Above Average), and catcher framing. It writes everything to one SQLite file in `data/`, with a target under 50 MB (GitHub's limit is 100 MB per file). Add a short data dictionary. * Evidence: row counts, plus spot-checks against published lines (for example, Vladdy's line through June 15 should match). * Done when: the spot-checks pass and the file size is safe. Get after it chief. Let me know if there are any issues or clarifications."
- Follow-up prompt: None yet.
- What was lacking after the first: Nothing material was lacking; the prompt named every data source, the output file and size target, the data dictionary, and the spot-check evidence.

## Phase 3 - Stats engine and tools

- Prompt typed: "Sweet. Let's move the chains and head to phase 3: Stats engine and tools * Key elements: plain Python functions, with no LLM involved, for: * stats as of the day before the game, using the 2025 fade; * left/right splits; * pitch arsenals; * how each batter does against each pitch type; * matchup scores; * the rotation predictor; * the opponent lineup predictor; * bullpen workload and availability; * sample-size flags. These become the agents' tools. * My recommendation: plain PydanticAI function tools instead of an MCP server. MCP adds a second process for graders to start, which is more 10-minute-rule risk, and the final project doesn't require it. * Evidence: * The rotation predictor's accuracy across every 2026 game, computed for free with no LLM. It's a great number for the report. * Unit tests for the blend math. Get after it and let me know about any issues or clarifications"
- Follow-up prompt: None yet.
- What was lacking after the first: Nothing material was lacking; the prompt listed every engine function, the tool approach, and the evidence to produce.
