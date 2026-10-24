import pytest

from engine.estimator import estimate, estimate_row

TOL = 0.05


def _row(age, qty=40.0, people=150, supply="insulin"):
    return {
        "scenario_id": "x",
        "site_supply": f"S04#{supply}",
        "site_id": "S04",
        "supply_id": supply,
        "sim_hour": 9,
        "last_reported_qty": qty,
        "last_report_hour": 9 - age,
        "report_age_h": age,
        "data_status": "live" if age < 1 else "stale",
        "people_served": people,
    }


def test_age_zero_collapses_range():
    r = estimate_row(_row(0))
    assert r["est_qty_p05"] == r["est_qty_p50"] == r["est_qty_p95"] == 40.0


def test_s04_age7_numbers():
    r = estimate_row(_row(7))
    assert r["burn_rate_per_h"] == pytest.approx(0.0625, abs=1e-6)
    assert r["est_qty_p50"] == pytest.approx(39.5625, abs=TOL)
    assert r["est_qty_p05"] == pytest.approx(21.14, abs=TOL)
    assert r["est_qty_p95"] == pytest.approx(57.99, abs=TOL)
    assert r["tts_p05_h"] == 72


def test_range_widens_with_age():
    widths = [estimate_row(_row(a))["est_qty_p95"] - estimate_row(_row(a))["est_qty_p05"] for a in range(0, 12)]
    assert all(b > a for a, b in zip(widths, widths[1:], strict=False))


def test_demo_hour9_estimates(demo_h9):
    rows, _ = demo_h9
    s02 = rows["S02#insulin"]
    assert s02["est_qty_p50"] == pytest.approx(0.761, abs=TOL)
    assert s02["est_qty_p05"] == pytest.approx(0.075, abs=TOL)
    assert s02["est_qty_p95"] == pytest.approx(1.447, abs=TOL)
    assert s02["tts_p05_h"] == pytest.approx(0.72, abs=TOL)
    s01 = rows["S01#insulin"]
    assert s01["est_qty_p05"] == pytest.approx(2.79, abs=TOL) and s01["tts_p05_h"] == pytest.approx(13.4, abs=TOL)
    assert rows["S03#insulin"]["est_qty_p05"] == pytest.approx(39.70, abs=TOL)
    assert rows["S03#insulin"]["tts_p05_h"] == 72


def test_zero_burn_tts_is_horizon():
    r = estimate([_row(3, people=0)])[0]
    assert r["tts_p05_h"] == r["tts_p50_h"] == r["tts_p95_h"] == 72
