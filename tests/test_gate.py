"""Safety gate R1-R5. OWNER: M4.  DRAFT by M3 for M4 review."""

from __future__ import annotations

from engine import estimator
from gate import rules
from gate.gate import evaluate_transfers
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import InventoryState, Transfer


def _inv(scenario):
    return estimator.estimate([InventoryState(**r) for r in store.query_pk(settings.table_inventory, scenario)])


def _t(n, src, dst, supply, qty, plan="plan_wildfire_demo_01_naive_h009"):
    return Transfer(transfer_id=f"{plan}_t{n:02d}", plan_id=plan, source_site_id=src, dest_site_id=dst,
                    supply_id=supply, qty=qty, priority_rank=n, distance_km=1.0)


def test_combine_precedence():
    assert rules.combine([None, None]) == ("APPROVE", [])
    assert rules.combine([(rules.R5, "REVIEW"), None])[0] == "REVIEW"
    d, ids = rules.combine([(rules.R5, "REVIEW"), (rules.R1, "BLOCK")])
    assert d == "BLOCK" and ids == [rules.R1, rules.R5]


def test_each_rule_alone():
    assert rules.r1_source_reserve(10, 7, 4.5) == (rules.R1, "BLOCK")
    assert rules.r1_source_reserve(10, 5, 4.5) is None
    assert rules.r2_dest_min_hours(5) == (rules.R2, "REVIEW")
    assert rules.r3_max_size(11, 20) == (rules.R3, "BLOCK")
    assert rules.r4_session_draw(13, 12.68) == (rules.R4, "BLOCK")
    assert rules.r4_session_draw(12, 12.68) == (rules.R4, "REVIEW")
    assert rules.r4_session_draw(6, 12.68) is None
    assert rules.r5_stale_source(7) == (rules.R5, "REVIEW")


def test_session_aware_catches_what_single_misses(demo_at_hour_9):
    inv = _inv(demo_at_hour_9)
    plan = [_t(1, "S04", "S01", "insulin", 6), _t(2, "S04", "S01", "insulin", 6), _t(3, "S04", "S02", "insulin", 6)]
    session = evaluate_transfers("sess_a", plan, inv, session_aware=True)
    single = evaluate_transfers("sess_b", plan, inv, session_aware=False)
    assert [t.decision for t in session] == ["REVIEW", "REVIEW", "BLOCK"]
    assert "BLOCK" not in [t.decision for t in single]  # the pitch: each looked fine alone


def test_history_carries_across_plans_in_a_session(demo_at_hour_9):
    inv = _inv(demo_at_hour_9)
    evaluate_transfers("sess_c", [_t(1, "S04", "S01", "insulin", 6, plan="plan_x_naive_h009")], inv)
    evaluate_transfers("sess_c", [_t(1, "S04", "S01", "insulin", 6, plan="plan_x_naive_h010")], inv)
    third = evaluate_transfers("sess_c", [_t(1, "S04", "S01", "insulin", 6, plan="plan_x_naive_h011")], inv)
    assert third[0].decision == "BLOCK"
    log = store.query_pk(settings.table_gate_log, "sess_c")
    assert len(log) == 3 and log[0]["cumulative_draw_limit"] > 0


def test_single_mode_writes_no_log(demo_at_hour_9):
    inv = _inv(demo_at_hour_9)
    evaluate_transfers("sess_d", [_t(1, "S04", "S01", "insulin", 6)], inv, session_aware=False)
    assert store.query_pk(settings.table_gate_log, "sess_d") == []


def test_bedrock_off_uses_templates(demo_at_hour_9):
    from engine.planner import run_plan

    plan = run_plan(demo_at_hour_9, 9, "naive", "sess_e")
    assert plan.explanation_source == "template"
    assert all(t.explanation_text for t in plan.transfers)
    blocked = [t for t in plan.transfers if t.decision == "BLOCK"]
    assert blocked and all("Blocked:" in t.explanation_text for t in blocked)
