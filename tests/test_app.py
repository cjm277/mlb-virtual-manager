"""The web app layer: API routes, the manager's edits + re-check, and role-based export packets (no LLM)."""

import io
import json
import shutil
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.agents.team import PACKETS
from backend.edits import LineupEdit, PlanEdits, apply_edits
from backend.export import export_zip
from backend.main import app

SAVED = Path(__file__).resolve().parents[1] / "evidence" / "logs" / "phase5_ui_run_2027"


@pytest.fixture
def run_dir(tmp_path, monkeypatch):
    """A copy of a real saved run, so edits don't touch the evidence."""
    d = tmp_path / SAVED.name
    shutil.copytree(SAVED, d)
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    return d


def lineup_of(run_dir: Path) -> list[LineupEdit]:
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    return [LineupEdit(slot=s["slot"], player_id=s["player_id"], position=s["position"])
            for s in plan["sections"]["lineup_card"]["lineup"]]


def test_unchanged_plan_still_passes(run_dir):
    plan = apply_edits(run_dir, PlanEdits())
    assert plan["checker"]["open_issues"] == []


def test_edit_that_breaks_the_rules_is_caught(run_dir):
    spots = lineup_of(run_dir)
    spots[1].position = spots[0].position                 # two players at one position
    plan = apply_edits(run_dir, PlanEdits(lineup=spots))
    assert any(i["code"] == "positions" for i in plan["checker"]["open_issues"])
    assert (run_dir / "plan_original.json").exists()      # the staff's original is kept


def test_legal_swap_passes_and_moves_the_starter_to_the_bench(run_dir):
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    card = plan["sections"]["lineup_card"]
    bench_hitter = next(b for b in card["bench"] if b["role"] != "backup_catcher")
    spots = lineup_of(run_dir)
    target = next(s for s in spots if s.position == "DH")  # anyone can DH
    benched = target.player_id
    target.player_id = bench_hitter["player_id"]
    plan = apply_edits(run_dir, PlanEdits(lineup=spots, staff_notes="Testing a swap."))
    assert plan["checker"]["open_issues"] == []
    assert plan["edited"] and plan["staff_notes"] == "Testing a swap."
    assert benched in {b["player_id"] for b in plan["sections"]["lineup_card"]["bench"]}


def test_unrested_or_unknown_starter_is_caught(run_dir):
    plan = apply_edits(run_dir, PlanEdits(starter_id=665489))   # Vladimir Guerrero Jr. is not a pitcher
    assert any(i["code"] == "starter_unavailable" for i in plan["checker"]["open_issues"])


def test_packets_only_contain_what_each_audience_may_see():
    plan = json.loads((SAVED / "plan.json").read_text(encoding="utf-8"))
    z = zipfile.ZipFile(io.BytesIO(export_zip(plan, PACKETS)))
    files = z.namelist()
    hitters = [f for f in files if f.startswith("hitters/")]
    pitchers = [f for f in files if f.startswith("pitchers/")]
    assert hitters and pitchers
    assert not any(k in f for f in hitters for k in ("pitching_plan", "medical", "opposing_hitters", "coaches_briefing"))
    assert not any(k in f for f in pitchers for k in ("lineup_card", "medical", "opposing_pitchers", "coaches_briefing"))
    assert any("medical_report.pdf" in f for f in files if f.startswith("coaches/"))
    assert all(z.read(f)[:4] == b"%PDF" for f in files if f.endswith(".pdf"))


def test_api_routes(run_dir):
    c = TestClient(app)
    assert len(c.get("/api/teams").json()["teams"]) == 30
    assert len(c.get("/api/games", params={"team_id": 141, "opponent_id": 111}).json()) == 26
    assert c.get(f"/api/runs/{run_dir.name}/plan").json()["status"] == "approved"
    assert c.get(f"/api/runs/{run_dir.name}/export").headers["content-type"] == "application/zip"
    assert c.get("/api/runs/..%2F..%2Fsecrets/plan").status_code in (400, 404)
    assert c.get("/api/not-a-route").status_code == 404
    assert c.post("/api/runs", json={"game_pk": 1, "team_id": 141}).status_code == 400   # unknown game
