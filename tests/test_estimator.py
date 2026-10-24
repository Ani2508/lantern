"""Estimator (contract 2.8, v1.2). OWNER: M3."""

from __future__ import annotations

import pytest

from engine.estimator import estimate_row
from lantern_core.schemas import InventoryState


def row(qty: float, age: float, people: int = 150, supply: str = "insulin") -> InventoryState:
    return InventoryState(
        scenario_id="t", site_supply=f"S04#{supply}", site_id="S04", supply_id=supply, sim_hour=9,
        last_reported_qty=qty, last_report_hour=9 - int(age), report_age_h=age,
        data_status="live" if age < 1 else "stale", people_served=people, updated_at="2026-11-07T17:00:00Z",
    )


def test_fresh_data_has_no_range():
    r = estimate_row(row(40, 0))
    assert r.est_qty_p05 == r.est_qty_p50 == r.est_qty_p95 == 40


def test_range_widens_with_age():
    w3 = estimate_row(row(40, 3))
    w7 = estimate_row(row(40, 7))
    assert (w7.est_qty_p95 - w7.est_qty_p05) > (w3.est_qty_p95 - w3.est_qty_p05) > 0


def test_demo_numbers_agreed_with_m2():
    """S04 insulin at hour 9: last count 40 vials, 7 h old (fixture README)."""
    r = estimate_row(row(40, 7))
    assert r.burn_rate_per_h == pytest.approx(0.0625)
    assert r.est_qty_p50 == pytest.approx(39.5625, abs=0.01)
    assert r.est_qty_p05 == pytest.approx(21.14, abs=0.01)
    assert r.est_qty_p95 == pytest.approx(57.98, abs=0.01)


def test_never_negative():
    r = estimate_row(row(5, 30))
    assert r.est_qty_p05 == 0 and r.est_qty_p50 >= 0
