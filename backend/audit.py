"""Append-only audit trail for one game-plan run: runs/<run_id>/audit.jsonl.

One JSON object per line, in the order things happened: run start, every agent start, every model step
(text, tool calls, tokens, timing, cost), every tool result, checker results, fix rounds, and the run total.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

PREVIEW_CHARS = 800


def preview(value: Any, limit: int = PREVIEW_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + f"... [{len(text) - limit} more chars]"


class Audit:
    def __init__(self, run_dir: Path, on_event: Callable[[dict], None] | None = None):
        self.run_dir = run_dir
        self.path = run_dir / "audit.jsonl"
        self.started = time.perf_counter()
        self.on_event = on_event
        run_dir.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, **fields: Any) -> dict:
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                  "t_plus_s": round(time.perf_counter() - self.started, 2), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        if self.on_event:
            self.on_event(record)
        return record
