"""Read-only access to the prebuilt data snapshot (data/mlb.sqlite)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "mlb.sqlite"
_local = threading.local()


def connect() -> sqlite3.Connection:
    """One read-only connection per thread (the app never writes to the snapshot)."""
    if not hasattr(_local, "con"):
        if not DB_PATH.exists():
            raise SystemExit(f"Data file not found: {DB_PATH}. It ships with the repo; re-clone if it is missing.")
        con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        con.row_factory = sqlite3.Row
        _local.con = con
    return _local.con


def rows(sql: str, *args) -> list[sqlite3.Row]:
    return connect().execute(sql, args).fetchall()


def one(sql: str, *args) -> sqlite3.Row | None:
    return connect().execute(sql, args).fetchone()
