"""Summarize game-plan runs (from runs/ or evidence/logs/) into one markdown table.

Usage:
  python scripts/summarize_runs.py                      # every run in runs/
  python scripts/summarize_runs.py evidence/logs        # saved evidence runs
  python scripts/summarize_runs.py runs --out evidence/logs/phase4_runs.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(run_dir: Path) -> dict | None:
    plan_file, audit_file = run_dir / "plan.json", run_dir / "audit.jsonl"
    if not plan_file.exists() or not audit_file.exists():
        return None
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    events = [json.loads(line) for line in audit_file.open(encoding="utf-8")]
    checks = [e for e in events if e["event"] == "checker" and e["round"] != "comms"]
    caught = sum(len(e["issues"]) for e in checks)
    return {
        "run": run_dir.name, "game": f"{plan['game']['game_date']} {plan['game']['team']} vs {plan['game']['opponent']}",
        "status": plan["status"], "fix_rounds": plan["checker"]["fix_rounds"], "issues_caught": caught,
        "tool_calls": sum(e["event"] == "tool_result" for e in events),
        "tool_refusals": sum(e["event"] == "tool_error" for e in events),
        **plan["usage"]["total"], "seconds": plan["usage"]["seconds"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "runs"))
    ap.add_argument("--out")
    args = ap.parse_args()
    rows = [r for d in sorted(Path(args.folder).iterdir()) if d.is_dir() and (r := load(d))]
    lines = ["| Game | Status | Fix rounds | Checker issues caught | Model calls | Tool calls (refused) | "
             "Input tokens (cached) | Output tokens | Cost (list price) | Time |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['game']} | {r['status']} | {r['fix_rounds']} | {r['issues_caught']} | {r['model_steps']} | "
                     f"{r['tool_calls']} ({r['tool_refusals']}) | {r['input_tokens']:,} ({r['cached_tokens']:,}) | "
                     f"{r['output_tokens']:,} | ${r['cost_usd']:.4f} | {r['seconds']}s |")
    if rows:
        n = len(rows)
        avg = lambda k: sum(r[k] for r in rows) / n  # noqa: E731
        lines.append(f"| **Average of {n}** | | {avg('fix_rounds'):.1f} | {avg('issues_caught'):.1f} | "
                     f"{avg('model_steps'):.0f} | {avg('tool_calls'):.0f} | {avg('input_tokens'):,.0f} "
                     f"({avg('cached_tokens'):,.0f}) | {avg('output_tokens'):,.0f} | ${avg('cost_usd'):.4f} | "
                     f"{avg('seconds'):.0f}s |")
    text = "\n".join(lines)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
