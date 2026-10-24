"""API routes in local mode (contract 2.10). OWNER: M1.  DRAFT by M3 for M1 review."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402

client = TestClient(app)
SID = "wildfire_demo_01"


def test_demo_flow():
    assert client.get("/api/health").json()["ok"] is True
    assert SID in client.get("/api/scenarios").json()
    assert client.post(f"/api/scenarios/{SID}/reset").json() == {"sim_hour": 0}
    assert client.post(f"/api/scenarios/{SID}/step", json={"to_hour": 9}).json() == {"sim_hour": 9}
    state = client.get(f"/api/scenarios/{SID}/state").json()
    assert state["sim_hour"] == 9 and len(state["sites"]) == 5

    naive = client.post(f"/api/scenarios/{SID}/plan", json={"planner": "naive", "apply_gate": True}).json()
    assert naive["counts"]["block"] >= 1
    lantern = client.post(f"/api/scenarios/{SID}/plan", json={"planner": "lantern"}).json()
    assert lantern["counts"]["block"] == 0 and len(lantern["scouts"]) == 2

    assert client.get(f"/api/plans/{naive['plan_id']}").json()["plan_id"] == naive["plan_id"]
    log = client.get(f"/api/sessions/{naive['session_id']}/gate-log").json()
    assert any(r["decision"] == "BLOCK" for r in log)


def test_errors_have_contract_shape():
    r = client.get("/api/scenarios/nope/state")
    assert r.status_code == 404 and set(r.json()) == {"error", "message"}
    assert client.get("/api/plans/garbage").status_code == 400
    assert client.post(f"/api/scenarios/{SID}/step", json={"to_hour": 99}).status_code == 400
