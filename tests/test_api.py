from fastapi.testclient import TestClient

from api.app import app
from lantern_core.config import BANNER
from lantern_core.schemas import FieldReportParse, GateLogRow, InventoryState, Plan, Site

DEMO = "wildfire_demo_01"
SAMPLE = "at central pharmacy now, counted 19 vials of insulin, fridge ok, line out the door"


def test_full_demo_through_api():
    client = TestClient(app)

    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json() == {"ok": True, "mode": "memory"}

    pub = client.get("/api/config/public").json()
    assert pub["banner"] == BANNER
    assert pub["planner_names"]["naive"] == "Naive AI (trusts old data)"
    assert pub["bedrock_enabled"] is False

    ids = client.get("/api/scenarios").json()
    assert DEMO in ids

    assert client.post(f"/api/scenarios/{DEMO}/reset").json() == {"sim_hour": 0}
    assert client.post(f"/api/scenarios/{DEMO}/step", json={"to_hour": 9}).json() == {"sim_hour": 9}

    state = client.get(f"/api/scenarios/{DEMO}/state").json()
    assert state["sim_hour"] == 9
    assert len(state["sites"]) == 5
    assert len(state["inventory"]) == 15
    for s in state["sites"]:
        Site.model_validate(s)
    for r in state["inventory"]:
        InventoryState.model_validate(r)

    naive = client.post(f"/api/scenarios/{DEMO}/plan", json={"planner": "naive", "apply_gate": True}).json()
    Plan.model_validate(naive)
    assert [t["decision"] for t in naive["transfers"]] == ["REVIEW", "REVIEW", "BLOCK"]
    assert naive["explanation_source"] == "template"

    fetched = client.get(f"/api/plans/{naive['plan_id']}").json()
    assert fetched["plan_id"] == naive["plan_id"]

    log = client.get(f"/api/sessions/{naive['session_id']}/gate-log").json()
    assert len(log) == 3
    for row in log:
        GateLogRow.model_validate(row)

    lantern = client.post(f"/api/scenarios/{DEMO}/plan", json={"planner": "lantern", "apply_gate": True}).json()
    Plan.model_validate(lantern)
    assert lantern["counts"]["block"] == 0
    assert len(lantern["scouts"]) == 2
    assert {s["site_id"] for s in lantern["scouts"]} == {"S04", "S02"}

    after = client.get(f"/api/scenarios/{DEMO}/state").json()
    assert set(after["latest_plans"]) == {"naive", "lantern"}

    parsed = client.post(f"/api/scenarios/{DEMO}/field-report", json={"text": SAMPLE}).json()
    FieldReportParse.model_validate(parsed)
    assert parsed["parser_source"] == "rules"
    assert (parsed["site_id"], parsed["supply_id"], parsed["qty"]) == ("S04", "insulin", 19)

    confirm = client.post(
        f"/api/scenarios/{DEMO}/field-report/confirm",
        json={
            "field_report_id": parsed["field_report_id"],
            "site_id": parsed["site_id"],
            "supply_id": parsed["supply_id"],
            "qty": parsed["qty"],
        },
    ).json()
    assert confirm["sim_hour"] == 9
    row = InventoryState.model_validate(confirm["inventory_row"])
    assert row.data_status == "live" and row.est_qty_p50 == 19

    replan = client.post(f"/api/scenarios/{DEMO}/plan", json={"planner": "lantern", "apply_gate": True}).json()
    assert any(t["source_site_id"] == "S04" for t in replan["transfers"])

    chart = client.get("/api/eval/proof-chart").json()
    assert "rows" in chart and "summary" in chart

    missing = client.get("/api/plans/plan_wildfire_demo_01_lantern_h099")
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"

    bad = client.post(f"/api/scenarios/{DEMO}/plan", json={"planner": "nope"})
    assert bad.status_code == 422


def test_single_check_and_events_routes():
    client = TestClient(app)
    client.post(f"/api/scenarios/{DEMO}/reset")

    events = client.get(f"/api/scenarios/{DEMO}/events").json()
    assert [e["type"] for e in events][:2] == ["hazard_start", "site_dark"]
    assert events[1]["site_ids"] == ["S02", "S04"]

    # the time-lapse steps one hour at a time
    for h in range(1, 10):
        assert client.post(f"/api/scenarios/{DEMO}/step", json={"to_hour": h}).json() == {"sim_hour": h}

    naive = client.post(f"/api/scenarios/{DEMO}/plan", json={"planner": "naive", "apply_gate": True}).json()
    single = client.get(f"/api/plans/{naive['plan_id']}/single-check").json()
    assert [r["transfer_id"] for r in single] == [t["transfer_id"] for t in naive["transfers"]]
    assert [r["decision"] for r in single] == ["REVIEW", "REVIEW", "REVIEW"]
