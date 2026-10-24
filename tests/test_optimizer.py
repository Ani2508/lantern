import pytest

from engine.optimizer import propose

TOL = 0.05


def _summary(ts):
    return [(t.source_site_id, t.dest_site_id, t.supply_id, round(t.qty, 2), t.priority_rank) for t in ts]


def test_naive_three_transfers_of_six_from_s04(demo_h9):
    rows, sites = demo_h9
    ts = propose(list(rows.values()), sites, "naive", "plan_wildfire_demo_01_naive_h009")
    assert _summary(ts) == [
        ("S04", "S01", "insulin", 6, 1),
        ("S04", "S02", "insulin", 6, 2),
        ("S04", "S01", "insulin", 6, 3),
    ]
    assert ts[2].transfer_id == "plan_wildfire_demo_01_naive_h009_t03"
    assert ts[0].distance_km == pytest.approx(1.05, abs=TOL)


def test_lantern_draws_from_s03_nothing_from_s04(demo_h9):
    rows, sites = demo_h9
    ts = propose(list(rows.values()), sites, "lantern", "plan_wildfire_demo_01_lantern_h009")
    assert _summary(ts) == [
        ("S03", "S02", "insulin", 6, 1),
        ("S03", "S01", "insulin", 6, 2),
        ("S03", "S01", "insulin", 6, 3),
    ]
    assert not [t for t in ts if t.source_site_id == "S04"]


def test_lantern_without_gate_awareness_would_overdraw(demo_h9):
    """Documents why the cap exists: S04 availability is capped at the R4 review band."""
    rows, sites = demo_h9
    s04 = rows["S04#insulin"]
    band = 0.8 * 0.6 * s04["est_qty_p05"] - 0.01
    assert band == pytest.approx(10.14, abs=TOL)


def test_lantern_after_field_report_draws_from_s04(demo_h9):
    rows, sites = demo_h9
    from engine.estimator import estimate_row

    r = dict(rows["S04#insulin"], last_reported_qty=19, last_report_hour=9, report_age_h=0, data_status="live")
    rows["S04#insulin"] = estimate_row(r)
    ts = propose(list(rows.values()), sites, "lantern", "plan_wildfire_demo_01_lantern_h009")
    from_s04 = [t.qty for t in ts if t.source_site_id == "S04"]
    assert from_s04 == [6, pytest.approx(3.11, abs=TOL)]
    assert all(t.source_site_id in ("S03", "S04") for t in ts)
    assert sum(from_s04) < 0.8 * 0.6 * 19


def test_session_draws_reduce_lantern_availability(demo_h9):
    rows, sites = demo_h9
    prior = {("S03", "insulin"): {"draw": 15.0, "count": 2, "p05_start": 39.7}}
    ts = propose(list(rows.values()), sites, "lantern", "plan_wildfire_demo_01_lantern_h010", prior)
    assert sum(t.qty for t in ts if t.source_site_id == "S03") <= 0.48 * 39.7 - 15.0


def test_max_transfers_and_min_qty(demo_h9, monkeypatch):
    from lantern_core.config import settings

    rows, sites = demo_h9
    monkeypatch.setattr(settings, "MAX_TRANSFERS_PER_PLAN", 2)
    assert len(propose(list(rows.values()), sites, "naive", "plan_x_naive_h009")) == 2
    with pytest.raises(ValueError):
        propose(list(rows.values()), sites, "bogus", "plan_x_naive_h009")
