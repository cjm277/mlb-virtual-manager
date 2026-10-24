"""Shared stats math: the 2025 fade, rates from counts, and sample-size flags.

Every number the agents see is computed here from raw counts. Nothing is invented by an LLM.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from backend import db

FADE_DAYS = 42  # 2025 stats fade out linearly over the first 6 weeks of 2026

# Count columns shared by the Statcast rollup tables.
COUNTS = ["pitches", "swings", "whiffs", "called_strikes", "zone_pitches", "chase_swings", "bip", "hard_hit",
          "barrels", "ev_n", "ev_sum", "pa", "ab", "h", "tb", "hr", "bb", "k", "hbp", "sf", "woba_den",
          "woba_num", "xwoba_num", "rv_sum"]
PITCH_GROUP = {
    "FF": "FB", "SI": "FB", "FC": "FB", "FA": "FB",
    "SL": "BRK", "ST": "BRK", "CU": "BRK", "KC": "BRK", "SV": "BRK", "CS": "BRK", "KN": "BRK",
    "CH": "OFF", "FS": "OFF", "FO": "OFF", "SC": "OFF",
}
GROUP_NAMES = {"FB": "fastballs", "BRK": "breaking balls", "OFF": "offspeed"}


# ---------------------------------------------------------------------------
# Dates and the 2025 fade
# ---------------------------------------------------------------------------

def to_date(d: str | date) -> date:
    return d if isinstance(d, date) else date.fromisoformat(d)


@lru_cache(maxsize=1)
def opening_day() -> date:
    return to_date(db.one("SELECT value FROM meta WHERE key = 'opening_day'")["value"])


def prior_weight(game_date: str | date, opening: date | None = None, fade_days: int = FADE_DAYS) -> float:
    """Share of weight on 2025 stats for a game on game_date.

    100% on Opening Day, falling in a straight line to 0% six weeks (42 days) later.
    """
    days_in = (to_date(game_date) - (opening or opening_day())).days
    return round(min(1.0, max(0.0, 1 - days_in / fade_days)), 4)


def day_before(game_date: str | date) -> str:
    return (to_date(game_date) - timedelta(days=1)).isoformat()


# ---------------------------------------------------------------------------
# Rates from counts
# ---------------------------------------------------------------------------

def _div(a: float, b: float) -> float | None:
    return a / b if b else None


def rates(c: dict) -> dict:
    """Turn summed counts into the rates the agents read."""
    obp_den = c["ab"] + c["bb"] + c["hbp"] + c["sf"]
    out_of_zone = c["pitches"] - c["zone_pitches"]
    return {
        "avg": _div(c["h"], c["ab"]),
        "obp": _div(c["h"] + c["bb"] + c["hbp"], obp_den),
        "slg": _div(c["tb"], c["ab"]),
        "woba": _div(c["woba_num"], c["woba_den"]),
        "xwoba": _div(c["xwoba_num"], c["woba_den"]),
        "k_pct": _div(100 * c["k"], c["pa"]),
        "bb_pct": _div(100 * c["bb"], c["pa"]),
        "whiff_pct": _div(100 * c["whiffs"], c["swings"]),
        "chase_pct": _div(100 * c["chase_swings"], out_of_zone),
        "csw_pct": _div(100 * (c["called_strikes"] + c["whiffs"]), c["pitches"]),
        "hard_hit_pct": _div(100 * c["hard_hit"], c["bip"]),
        "barrel_pct": _div(100 * c["barrels"], c["bip"]),
        "avg_ev": _div(c["ev_sum"], c["ev_n"]),
        "rv_per_100": _div(100 * c["rv_sum"], c["pitches"]),  # hitter's point of view
    }


def blend_rates(cur: dict | None, prior: dict | None, w_prior: float) -> tuple[dict, float]:
    """Blend 2026 and 2025 rates with the fade weight.

    - Both seasons available: weighted average, stat by stat.
    - Only one season available (rookie, or no 2026 games yet): use that season alone.
    Returns (rates, weight actually put on 2025).
    """
    if not prior:
        w_prior = 0.0
    elif not cur:
        w_prior = 1.0
    blended = {}
    for key in (cur or prior or {}):
        a = cur.get(key) if cur else None
        b = prior.get(key) if prior else None
        if a is None and b is None:
            blended[key] = None
        elif b is None or w_prior == 0:
            blended[key] = a if a is not None else b
        elif a is None or w_prior == 1:
            blended[key] = b
        else:
            blended[key] = (1 - w_prior) * a + w_prior * b
    return blended, w_prior


# ---------------------------------------------------------------------------
# Sample-size flags
# ---------------------------------------------------------------------------

# (small below, moderate below) for each kind of sample.
THRESHOLDS = {"pa": (60, 200), "pitches": (300, 1000), "pitch_type": (50, 200), "pitches_seen": (100, 300)}


def sample_flag(n: float, kind: str) -> str:
    small, moderate = THRESHOLDS[kind]
    return "small" if n < small else "moderate" if n < moderate else "ok"


def effective_n(n_cur: float, n_prior: float, w_prior: float) -> float:
    """Sample size behind a blended number (each season's sample weighted by its share)."""
    return (1 - w_prior) * n_cur + w_prior * n_prior


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

THREE_PLACES = {"avg", "obp", "slg", "woba", "xwoba"}


def tidy(r: dict) -> dict:
    """Round for display: .xxx for slash/wOBA stats, one decimal for percentages and the rest."""
    out = {}
    for k, v in r.items():
        if v is None:
            out[k] = None
        elif k in THREE_PLACES:
            out[k] = round(v, 3)
        elif isinstance(v, float):
            out[k] = round(v, 1)
        else:
            out[k] = v
    return out


def sum_counts(sql: str, *args) -> dict:
    """Run a SELECT of SUM(col) AS col for every count column; missing rows give zeros."""
    row = db.one(sql, *args)
    return {c: (row[c] or 0) if row else 0 for c in COUNTS}


SUM_SELECT = ", ".join(f"SUM({c}) AS {c}" for c in COUNTS)


@lru_cache(maxsize=256)
def league_rates(game_date: str) -> dict:
    """League-wide hitting rates before game_date (blended with 2025 the same way), for context."""
    w = prior_weight(game_date)
    cur = sum_counts(f"SELECT {SUM_SELECT} FROM statcast_batter_game WHERE game_date < ?", game_date)
    prior = sum_counts(f"SELECT {SUM_SELECT} FROM statcast_batter_season WHERE season = 2025")
    blended, _ = blend_rates(rates(cur) if cur["pa"] else None, rates(prior), w)
    return blended
