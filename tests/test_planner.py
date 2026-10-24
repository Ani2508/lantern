"""run_plan end to end in local mode. OWNER: M3."""

from __future__ import annotations

from engine.planner import run_plan
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import Plan


def test_lantern_plan_is_saved_with_scouts(demo_at_hour_9):
    plan = run_plan(demo_at_hour_9, 9, "lantern", "sess_t_lantern")
    assert plan.plan_id == "plan_wildfire_demo_01_lantern_h009"
    assert plan.data_loss_pct == 40.0
    assert len(plan.scouts) == 2
    assert "S04" in {s.site_id for s in plan.scouts}
    saved = store.get_item(settings.table_plans, {"scenario_id": demo_at_hour_9, "plan_id": plan.plan_id})
    assert Plan(**saved).plan_id == plan.plan_id
    inv = store.get_item(settings.table_inventory, {"scenario_id": demo_at_hour_9, "site_supply": "S04#insulin"})
    assert round(inv["est_qty_p05"], 2) == 21.14


def test_all_three_planners_run(demo_at_hour_9):
    for planner in ("equal_split", "naive", "lantern"):
        plan = run_plan(demo_at_hour_9, 9, planner, f"sess_t_{planner}", apply_gate=False)
        assert plan.planner == planner
        assert all(t.decision is None for t in plan.transfers)


def test_notify_off_writes_no_fallback(demo_at_hour_9):
    run_plan(demo_at_hour_9, 9, "lantern", "sess_t")
    try:
        store.get_object("fallback/plan.json")
        found = True
    except KeyError:
        found = False
    assert not found


def test_notify_on_writes_fallback(demo_at_hour_9, monkeypatch):
    monkeypatch.setattr(settings, "notify_enabled", True)
    run_plan(demo_at_hour_9, 9, "lantern", "sess_t")
    assert store.get_json("fallback/plan.json")["planner"] == "lantern"


def test_handler(demo_at_hour_9):
    from engine.handler import lambda_handler

    out = lambda_handler({"scenario_id": demo_at_hour_9, "sim_hour": 9, "planner": "naive",
                          "session_id": "sess_h", "apply_gate": True}, None)
    assert out["plan_id"] == "plan_wildfire_demo_01_naive_h009"
