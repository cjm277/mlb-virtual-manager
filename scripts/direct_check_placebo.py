"""Placebo for the direct check: score the real manager's PREVIOUS-game lineup (same team) against today's real lineup.
Both are the manager's own choices; yesterday's simply wasn't used today. If the direct (after-the-game) lens is
unbiased, this should be about zero (a little negative for whatever the manager learned overnight)."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import value_verification as vv  # noqa: E402
import win_model as wm  # noqa: E402
from backend.engine import roster  # noqa: E402
from backend.engine.matchups import batting_side  # noqa: E402

wm.load_constants()
rng = np.random.default_rng(409)
feats = sorted(json.loads(wm.FEATURES.read_text(encoding="utf-8")), key=lambda g: (g["date"], g["game_pk"]))
last = {}
cases = []
for g in feats:
    for us, them in (("home", "away"), ("away", "home")):
        tid = g[us + "_id"]
        prev = last.get(tid)
        last[tid] = (g, us)
        if not prev or len(g[us]["lineup"]) != 9:
            continue
        pg, pus = prev
        d = g["date"]
        active = {r["player_id"] for r in roster.active_roster(tid, d)}
        plu = pg[pus]["lineup"]
        ppos = wm.real_positions(pg["game_pk"], tid)
        if len(plu) != 9 or len(ppos) != 9 or not all(e["pid"] in active for e in plu):
            continue
        rpos = wm.real_positions(g["game_pk"], tid)
        opos = wm.real_positions(g["game_pk"], g[them + "_id"])
        if len(rpos) != 9 or len(opos) != 9:
            continue
        throws = wm.hand(g[them]["sp"]["pid"])[1] or "R"
        plan = []
        for e in plu:
            w, n = wm.hitter(e["pid"], d)
            plan.append({"pid": e["pid"], "slot": e["slot"], "woba": w, "n": n,
                         "edge": batting_side(wm.hand(e["pid"])[0], throws) != throws})
        cases.append({"date": d, "team_id": tid, "home": us == "home", "real": {"lineup": g[us]["lineup"], "sp": g[us]["sp"]},
                      "opp_real": g[them]["lineup"], "opp_vs_plan_sp": g[them]["lineup"], "opp_sp": g[them]["sp"],
                      "opp_pos": opos, "real_pos": rpos, "plan": {"lineup": plan, "sp": g[us]["sp"]},
                      "plan_pos": {e["pid"]: ppos[e["pid"]] for e in plu}})
print(len(cases), "team-games with yesterday's nine all active today")
changed = np.array([{e["pid"] for e in c["plan"]["lineup"]} != {e["pid"] for e in c["real"]["lineup"]} or
                    any(c["plan_pos"][p] != c["real_pos"].get(p) for p in c["plan_pos"]) for c in cases])
F = vv.Future(100, 200)
FL = {"hitter": F.hitter, "pitcher": F.pitcher, "defense": F.defense}
S = {"hitter": vv.season_hitter, "pitcher": vv.season_pitcher, "defense": vv.season_defense}
ind = vv.split_lineup(cases, FL)
pre = vv.split_lineup(cases, S)
out = {}
for name, m in (("all", np.ones(len(cases), bool)), ("lineup or positions changed", changed)):
    r = {}
    for lab, x in (("direct offense", ind["offense"]), ("direct defense", ind["defense"]),
                   ("direct total", ind["offense"] + ind["defense"]), ("pre-game season lens", pre["offense"] + pre["defense"])):
        v = x[m]
        r[lab] = [round(162 * v.mean(), 2), *[round(162 * y, 2) for y in vv.boot(v, rng)]]
    out[name] = dict(n=int(m.sum()), **r)
print(json.dumps(out, indent=1))
(ROOT / "evidence" / "logs" / "value_at_scale" / "placebo.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
