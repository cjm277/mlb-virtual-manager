"""Where does the direct-check defense gap come from? Plan minus real, runs per game, split by how many innings the
fielder actually played at that position in 2026 (the direct lens's sample), and catcher framing separately.
Also: the same gap with each fielder's 2026 rate regressed toward his PRE-GAME rating at 600 innings (kills the
small-sample / benched-after-a-bad-start noise in unregressed 2026 rates)."""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import value_verification as vv  # noqa: E402
import win_model as wm  # noqa: E402
from backend import db  # noqa: E402
from backend.engine import defense as dfn  # noqa: E402

wm.load_constants()
F = vv.Future(100, 200)
built = json.loads((ROOT / "evidence/logs/value_at_scale/lineups.json").read_text(encoding="utf-8"))
feats = {g["game_pk"]: g for g in json.loads(wm.FEATURES.read_text(encoding="utf-8"))}
inn26 = {(r["player_id"], r["position"]): r["innings"] or 0.0 for r in db.rows("SELECT * FROM fielding_by_position WHERE season = 2026")}


def band(pid, pos):
    i = inn26.get((pid, pos), 0.0)
    return "0 (prior)" if i < 1 else "1-99" if i < 100 else "100-499" if i < 500 else "500+"


def regressed(pid, pos):
    frp_inn = F.field.get((pid, pos))
    pre = dfn.fielding_per_game(pid, pos, 2025)
    if not frp_inn or frp_inn[1] < 1:
        return F.defense(pid, pos, "")
    frp, inn = frp_inn
    return (9 * frp + pre * 600) / (inn + 600)


res = {}
for v in ("before", "marcel", "after"):
    tot = defaultdict(float); cnt = defaultdict(float); reg = 0.0; frm = 0.0; n = 0
    for b in built:
        g = feats.get(b["game_pk"])
        if not g or v not in b["lineups"]:
            continue
        rp = wm.real_positions(b["game_pk"], b["team_id"])
        if len(rp) != 9:
            continue
        n += 1
        plan = {p: pos for _, p, pos in b["lineups"][v]}
        for side, s in ((plan, 1), (rp, -1)):
            for p, pos in side.items():
                if pos in ("DH", "P"):
                    continue
                if pos == "C":
                    frm += s * F.defense(p, "C", "")
                    continue
                tot[band(p, pos)] += s * F.defense(p, pos, "")
                cnt[band(p, pos)] += s
                reg += s * regressed(p, pos)
    res[v] = {"games": n, "fielding_by_2026_innings_runs_per_game": {k: round(x / n, 4) for k, x in sorted(tot.items())},
              "net_fielders_by_band_per_game": {k: round(x / n, 3) for k, x in sorted(cnt.items())},
              "fielding_total": round(sum(tot.values()) / n, 4), "framing": round(frm / n, 4),
              "fielding_regressed_to_pregame_at_600": round(reg / n, 4)}
print(json.dumps(res, indent=1))
(ROOT / "evidence/logs/value_at_scale/defense_gap.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
