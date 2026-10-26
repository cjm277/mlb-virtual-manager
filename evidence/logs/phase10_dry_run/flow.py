"""Use the web app from a fresh clone the way the browser does: the same HTTP calls the React screens make.
Load the page and its scripts -> pick team, opponent, game -> build a plan (watch the staff) -> dropdown edit ->
chat edit -> download the packets ZIP. Prints one line per step with its time."""
import io
import json
import re
import sys
import time
import zipfile

import requests

B = "http://127.0.0.1:8000"
t0 = time.time()
ok = True


def step(name, fn):
    global ok
    s = time.time()
    try:
        msg = fn()
        print(f"PASS  {name}  ({time.time() - s:.1f} s)  {msg}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"FAIL  {name}  ({time.time() - s:.1f} s)  {type(e).__name__}: {e}")
        raise SystemExit(1)


S = {}


def page():
    r = requests.get(B + "/", timeout=10)
    r.raise_for_status()
    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', r.text)
    for a in assets:
        requests.get(B + a, timeout=10).raise_for_status()
    return f"home page + {len(assets)} script/style files loaded"


def pick():
    teams = requests.get(B + "/api/teams", timeout=10).json()["teams"]
    tor = next(t for t in teams if t["abbrev"] == "TOR")
    bos = next(t for t in teams if t["abbrev"] == "BOS")
    games = requests.get(B + f"/api/games?team_id={tor['team_id']}&opponent_id={bos['team_id']}", timeout=20).json()
    g = next(x for x in games if x.get("game_date") == "2027-05-03")
    S.update(team=tor["team_id"], game=g["game_pk"])
    return f"{len(teams)} teams; TOR vs BOS has {len(games)} games; picked 2027-05-03 (game {g['game_pk']})"


def build():
    r = requests.post(B + "/api/runs", json={"game_pk": S["game"], "team_id": S["team"]}, timeout=30).json()
    S["run"] = r["run_id"]
    since, agents = 0, set()
    while True:
        e = requests.get(B + f"/api/runs/{S['run']}/events?since={since}", timeout=30).json()
        since = e["next"]
        agents |= {x.get("agent") for x in e["events"] if x.get("agent")}
        if e["error"]:
            raise RuntimeError(e["error"])
        if e["done"]:
            break
        time.sleep(1)
    p = requests.get(B + f"/api/runs/{S['run']}/plan", timeout=30).json()
    S["plan"] = p
    u = p["usage"]["total"]
    return (f"status {p['status']}; {len(agents)} staff seen working ({', '.join(sorted(agents))}); "
            f"{u['model_steps']} model calls, ${u['cost_usd']:.4f}, {p['usage']['seconds']} s; "
            f"starter {p['sections']['pitching_plan']['starter']['name']}")


def dropdown():
    requests.get(B + f"/api/runs/{S['run']}/options", timeout=30).raise_for_status()
    lu = [{"slot": x["slot"], "player_id": x["player_id"], "position": x["position"]}
          for x in S["plan"]["sections"]["lineup_card"]["lineup"]]
    a = next(x for x in lu if x["slot"] == 1)
    b = next(x for x in lu if x["slot"] == 2)
    a["slot"], b["slot"] = 2, 1                      # swap the top two in the order
    r = requests.post(B + f"/api/runs/{S['run']}/edits", json={"lineup": lu}, timeout=60)
    r.raise_for_status()
    p = requests.get(B + f"/api/runs/{S['run']}/plan", timeout=30).json()
    top = sorted(p["sections"]["lineup_card"]["lineup"], key=lambda x: x["slot"])[0]
    issues = p.get("checker", {}).get("issues", [])
    return f"swapped slots 1 and 2; new leadoff {top['name']}; re-checked by code: {len(issues)} issue(s); edited={p.get('edited')}"


def chat():
    r = requests.post(B + f"/api/runs/{S['run']}/chat",
                      json={"message": "Why is our cleanup hitter batting 4th?"}, timeout=180).json()
    return f"assistant replied ({r.get('status')}): {str(r.get('reply') or r.get('text') or r)[:110]}..."


def export():
    r = requests.get(B + f"/api/runs/{S['run']}/export", timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    folders = sorted({n.split("/")[0] for n in names if "/" in n})
    return f"ZIP {len(r.content) // 1024} KB, {len(names)} files, folders {folders}"


step("Open the app", page)
step("Pick team, opponent and game", pick)
step("Build game plan", build)
step("Edit with the dropdowns", dropdown)
step("Chat with the assistant coach", chat)
step("Download packets (ZIP)", export)
print(f"ALL STEPS PASSED in {time.time() - t0:.1f} s" if ok else "FAILED")
