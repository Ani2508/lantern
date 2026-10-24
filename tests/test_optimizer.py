"""Optimizer modes on the demo scenario at hour 9. OWNER: M3."""

from __future__ import annotations

from engine import estimator, optimizer
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import InventoryState


def _inputs(scenario):
    inv = estimator.estimate([InventoryState(**r) for r in store.query_pk(settings.table_inventory, scenario)])
    sites = {s["site_id"]: s for s in store.query_pk(settings.table_sites, scenario)}
    return inv, sites


def test_naive_drains_the_stale_pharmacy(demo_at_hour_9):
    inv, sites = _inputs(demo_at_hour_9)
    res = optimizer.propose(inv, sites, "plan_x_naive_h009", "naive")
    from_s04 = [t for t in res.transfers if t.source_site_id == "S04" and t.supply_id == "insulin"]
    assert len(from_s04) >= 3
    assert [t.qty for t in from_s04[:3]] == [6, 6, 1]  # cooler box = 6 vials
    assert all(t.qty <= settings.transfer_unit_cap["insulin"] for t in from_s04)


def test_lantern_never_uses_stale_sources(demo_at_hour_9):
    inv, sites = _inputs(demo_at_hour_9)
    stale = {r.site_id for r in inv if r.report_age_h > settings.gate_stale_review_h}
    res = optimizer.propose(inv, sites, "plan_x_lantern_h009", "robust")
    assert res.transfers
    assert not any(t.source_site_id in stale for t in res.transfers)
    assert ("S04", "insulin") in res.skipped_stale_sources


def test_lantern_stays_under_gate_limits(demo_at_hour_9):
    inv, sites = _inputs(demo_at_hour_9)
    est = {(r.site_id, r.supply_id): r for r in inv}
    res = optimizer.propose(inv, sites, "plan_x_lantern_h009", "robust")
    drawn: dict = {}
    for t in res.transfers:
        src = est[(t.source_site_id, t.supply_id)]
        assert t.qty <= settings.gate_max_transfer_frac * src.est_qty_p05
        drawn[(t.source_site_id, t.supply_id)] = drawn.get((t.source_site_id, t.supply_id), 0) + t.qty
    for k, total in drawn.items():
        limit = settings.gate_session_draw_frac * est[k].est_qty_p05
        assert total <= settings.gate_session_review_frac * limit + 1e-9


def test_max_transfers(demo_at_hour_9):
    inv, sites = _inputs(demo_at_hour_9)
    for mode in ("robust", "naive"):
        res = optimizer.propose(inv, sites, "p", mode)
        assert len(res.transfers) <= settings.max_transfers_per_plan
        assert [t.priority_rank for t in res.transfers] == list(range(1, len(res.transfers) + 1))
