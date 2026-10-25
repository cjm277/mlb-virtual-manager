"""Value the season-aware starter rule (backend/engine/starter_rule.py) by replaying every team's 2026 season (no LLM).

Each team's schedule is replayed in order. Every game, the rule picks our starter from the team's rotation that
day (pitchers who made a real start for the team in the 15 days before, on the active roster), using the REPLAYED
rest and start counts: a start the rule gives a pitcher today uses up his rest for the games that follow, so moving
the ace up a day is never counted as free. Policies compared:

  rule      the app's rule: best rested starter (4+ days of rest), at most 2 starts beyond his fair share
  no cap    the same without the extra-start cap
  in turn   a plain rotation: the longest-rested starter every game (the "do nothing clever" baseline)

Each game is scored against the starter who really pitched, in runs:
  - season lens: his wOBA allowed regressed at 400 batters faced, over his usual share of the game (the yardstick
    the verified estimate uses; its within-team slope against real runs is 0.76, value_verification.md Check 2);
  - Marcel: the projection the rule itself ranks by;
  - after the game: what each pitcher allowed over the rest of 2026 (no pre-game number).
Verified wins = season-lens runs saved x the within-team slope x win probability per run x 162.

Usage: python scripts/starter_rule_replay.py      (a few minutes; writes evidence/tests/starter_rule.md)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backend import db  # noqa: E402

SAVE = ROOT / "evidence" / "logs" / "starter_rule"
REPORT = ROOT / "evidence" / "tests" / "starter_rule.md"
NOTES = ROOT / "evidence" / "tests" / "starter_rule_interpretation.md"
CAPS = (0, 1, 2, 3, 4, 6)
POLICIES = {"in_turn": "Plain rotation (longest-rested starter)",
            **{f"cap{c}": f"Rule, at most {c} extra start{'s' if c != 1 else ''}" for c in CAPS},
            "no_cap": "Rule, no extra-start cap"}
SEED = 409


def days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def replay_team(team_id: int) -> dict:
    import value_verification as vv
    import win_model as wm
    from backend.engine import starter_rule as sr
    wm.load_constants()
    fut = vv.Future(0, 200)
    games = db.rows("""SELECT g.game_pk, g.game_date d, g.game_number gn, p.player_id real, p.bf
                       FROM games g JOIN pitching_lines p ON p.game_pk = g.game_pk AND p.team_id = ? AND p.is_starter = 1
                       WHERE g.home_team_id = ? OR g.away_team_id = ? ORDER BY g.game_date, g.game_number""",
                    team_id, team_id, team_id)
    real_starts = [(r["d"], r["real"]) for r in games if (r["bf"] or 0) >= sr.REAL_START_BF]
    real_count = defaultdict(int)
    for r in games:
        real_count[r["real"]] += 1

    def season_cost(p, d):
        return vv.runs_vs_starter(wm.shrink(*wm.pitcher(p, d), 400), wm.starter_depth(p, d))

    def future_cost(p, d):
        return vv.runs_vs_starter(fut.pitcher({"pid": p}, d), wm.starter_depth(p, d))

    out = {}
    for pol in POLICIES:
        last, starts, first, active_games = {}, defaultdict(int), {}, defaultdict(int)
        rows = []
        for g in games:
            d = g["d"]
            lo = (date.fromisoformat(d) - timedelta(days=sr.ROTATION_WINDOW)).isoformat()
            members = sorted({p for x, p in real_starts if lo <= x < d and sr._active(team_id, p, d)})
            for p in members:
                first.setdefault(p, d)
            cycle = sr.team_cycle(team_id, d, g["gn"] or 1)
            fair = {p: (active_games[p] + 1) / cycle for p in members}
            if members:
                cost = {p: sr.starter_cost(p, d) for p in members}
                if pol == "no_cap":
                    fair = {p: 1e6 for p in members}
                elif pol.startswith("cap"):           # shift the fair share so the cap is `c` extra starts
                    fair = {p: v - sr.EXTRA_STARTS + int(pol[3:]) for p, v in fair.items()}
                c = sr.choose(members, last, starts, fair, cost, d)
                pick = c["on_turn"] if pol == "in_turn" else c["pick"]
            else:
                pick = g["real"]          # season start, before any rotation exists: use the real starter
            real = g["real"]
            rows.append({"d": d, "pick": pick, "real": real, "changed": pick != real,
                         "four_day": pick in last and days(last[pick], d) == 5,
                         "season": season_cost(pick, d) - season_cost(real, d),
                         "marcel": sr.starter_cost(pick, d) - sr.starter_cost(real, d),
                         "future": future_cost(pick, d) - future_cost(real, d)})
            last[pick] = d
            starts[pick] += 1
            for p in first:
                if sr._active(team_id, p, d):
                    active_games[p] += 1
        extra = {p: starts[p] - real_count.get(p, 0) for p in starts}
        out[pol] = {"rows": rows, "extra": extra}
    return {"team_id": team_id, "policies": out}


def marcel_starter_slope(rng) -> dict:
    """Runs actually scored on the opposing starter's Marcel quality, with team fixed effects (only game-to-game
    changes of starter within a team identify it), exactly as value_verification.py Check 2 does for the season lens."""
    import value_verification as vv
    from backend.engine import winmodel
    winmodel.set_version("marcel")
    lens = {"hitter": vv.season_hitter, "pitcher": lambda sp, d: winmodel.starter_quality(sp["pid"], d),
            "defense": vv.season_defense}
    rows = vv.team_game_table(lens)
    s = vv.slopes(rows, rng)
    late = vv.slopes([r for r in rows if r["date"] >= vv.TEST_FROM], rng, n_boot=200)
    return {"point": s["point"][1], "ci": [s["ci_low"][1], s["ci_high"][1]], "aug_sep": late["point"][1],
            "aug_sep_ci": [late["ci_low"][1], late["ci_high"][1]]}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    import value_verification as vv
    import win_model as wm
    wm.load_constants()
    SAVE.mkdir(parents=True, exist_ok=True)
    teams = [r["team_id"] for r in db.rows("SELECT team_id FROM teams ORDER BY team_id")]
    res = []
    with Pool(8) as pool:
        for i, r in enumerate(pool.imap_unordered(replay_team, teams), 1):
            res.append(r)
            print(f"  {i}/{len(teams)} teams", flush=True)
    res.sort(key=lambda r: r["team_id"])
    (SAVE / "replay.json").write_text(json.dumps(res), encoding="utf-8")

    saved = json.loads(vv.OUT_JSON.read_text(encoding="utf-8"))
    sl = saved["slopes"]["all"]
    slope, slo, shi = sl["point"][1], sl["ci_low"][1], sl["ci_high"][1]
    P = wm.Params()
    r0 = wm.LG_RPG
    wpr = (wm.win_prob(r0, r0 - 0.01, True, P) + wm.win_prob(r0, r0 - 0.01, False, P)
           - wm.win_prob(r0, r0 + 0.01, True, P) - wm.win_prob(r0, r0 + 0.01, False, P)) / 0.04
    rng = np.random.default_rng(SEED)
    ms = marcel_starter_slope(rng)
    print("Marcel starter slope", ms, flush=True)
    summary = {"slope": [slope, slo, shi], "marcel_slope": ms, "wp_per_run": wpr, "policies": {}}
    for pol in POLICIES:
        per_team = {r["team_id"]: r["policies"][pol]["rows"] for r in res}
        allrows = [x for v in per_team.values() for x in v]
        n = len(allrows)
        saved_runs = {k: -np.mean([x[k] for x in allrows]) for k in ("season", "marcel", "future")}
        # Interval: resample whole team-seasons, and draw the within-team slope from its range
        tids = list(per_team)
        sims = []
        for _ in range(2000):
            pick = rng.integers(0, len(tids), len(tids))
            rr = [x for i in pick for x in per_team[tids[i]]]
            s = rng.normal(slope, (shi - slo) / 3.92)
            sm = rng.normal(ms["point"], (ms["ci"][1] - ms["ci"][0]) / 3.92)
            sims.append((-np.mean([x["season"] for x in rr]) * s * wpr * 162, -np.mean([x["marcel"] for x in rr]) * sm * wpr * 162))
        extras = [e for r in res for e in r["policies"][pol]["extra"].values()]
        top = [max(r["policies"][pol]["extra"].values()) for r in res]
        summary["policies"][pol] = {
            "games": n, "changed": float(np.mean([x["changed"] for x in allrows])),
            "four_day": float(np.mean([x["four_day"] for x in allrows])),
            "runs_saved_per_game": saved_runs,
            "season_lens_wins": saved_runs["season"] * slope * wpr * 162,
            "season_lens_ci": np.percentile([a for a, _ in sims], [2.5, 97.5]).tolist(),
            "verified_wins": saved_runs["marcel"] * ms["point"] * wpr * 162,
            "verified_ci": np.percentile([b for _, b in sims], [2.5, 97.5]).tolist(),
            "future_wins": saved_runs["future"] * wpr * 162,
            "top_gainer_extra_mean": float(np.mean(top)), "top_gainer_extra_max": int(max(top)),
            "pitchers_more_than_2_extra": int(sum(e > 2 for e in extras)),
        }
    real4 = db.one("""WITH s AS (SELECT player_id, game_date, LAG(game_date) OVER (PARTITION BY player_id ORDER BY game_date) prev
                      FROM pitching_lines WHERE is_starter = 1) SELECT AVG(julianday(game_date) - julianday(prev) = 5) x
                      FROM s WHERE prev IS NOT NULL""")["x"]
    summary["real_four_day"] = real4
    summary["old_starter_piece"] = 162 * saved["verified"]["parts"]["starter"]
    summary["old_greedy_replay"] = saved.get("replay")
    (SAVE / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    REPORT.write_text(render(summary), encoding="utf-8")
    print(render(summary))


def render(s: dict) -> str:
    f = lambda x: f"{x:+.2f}"  # noqa: E731
    P = s["policies"]
    L = [
        "# The season-aware starter rule, replayed over every 2026 season",
        "",
        "Generated by `scripts/starter_rule_replay.py` (no LLM calls, $0); the rule is `backend/engine/starter_rule.py`, "
        "the same code the app's `model_starter` tool runs. Every team's 2026 schedule is replayed in order; each start "
        "the rule makes uses up that pitcher's rest for the games that follow. Compared with the starter who really "
        "pitched. Wins per 162 games.",
        "",
        "**Verified wins**, valued the same way as the lineup's offense: runs saved on the Marcel projection the rule "
        f"ranks by, times Marcel's own within-team slope against real runs ({s['marcel_slope']['point']:.2f}, "
        f"{s['marcel_slope']['ci'][0]:.2f} to {s['marcel_slope']['ci'][1]:.2f}; August-September only "
        f"{s['marcel_slope']['aug_sep']:.2f}), times {s['wp_per_run']:.3f} win probability per run, times 162. The older "
        f"season-stats lens (slope {s['slope'][0]:.2f}) is shown for reference. Intervals resample whole team-seasons and "
        "the slope.",
        "",
        "| Policy | **Verified wins** | Season-stats lens | Judged on rest-of-season results | Starts on exactly 4 days' rest | "
        "Top gainer per team: extra starts vs real (mean / max) |",
        "|---|---|---|---|---|---|",
        *[f"| {POLICIES[k]} | **{f(v['verified_wins'])}** ({f(v['verified_ci'][0])} to {f(v['verified_ci'][1])}) | "
          f"{f(v['season_lens_wins'])} | {f(v['future_wins'])} | {v['four_day']:.0%} | "
          f"{v['top_gainer_extra_mean']:+.1f} / {v['top_gainer_extra_max']:+d} |" for k, v in P.items()],
        "",
        f"Real 2026 starters started on exactly 4 days' rest in {s['real_four_day']:.0%} of starts.",
        "",
        f"For comparison: the starter piece in the earlier verification was **{f(s['old_starter_piece'])}** wins (the "
        "Pitching Coach's own choices on 150 plans, scaled down for the season-replay share that survives).",
        "",
    ]
    if NOTES.exists():
        L += [NOTES.read_text(encoding="utf-8")]
    return "\n".join(L)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":        # re-render from the saved summary
        REPORT.write_text(render(json.loads((SAVE / "summary.json").read_text(encoding="utf-8"))), encoding="utf-8")
    else:
        main()
