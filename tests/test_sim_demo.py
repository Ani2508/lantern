import json

import pytest

from lantern_core import store
from lantern_core.config import settings
from simulator import run
from simulator.generator import truth_key
from tests.conftest import FIXTURE_DIR

DEMO = "wildfire_demo_01"
TOL = 0.05


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture
def demo_h9():
    assert run.reset(DEMO) == 0
    run.step(DEMO, 9)
    return {r["site_supply"]: r for r in store.query_pk(settings.TABLE_INVENTORY, DEMO)}


def test_simulator_reproduces_fixture_reports_and_truth(demo_h9):
    for h in range(10):
        got = store.get_jsonl(f"raw/scenarios/{DEMO}/reports/h{h:03d}.jsonl")
        assert got == _jsonl(FIXTURE_DIR / "reports" / f"h{h:03d}.jsonl"), f"hour {h}"
    assert store.get_jsonl(truth_key(DEMO)) == _jsonl(FIXTURE_DIR / "truth" / "stock.jsonl")


def test_hour9_matches_readme(demo_h9):
    inv = demo_h9
    expected = {
        "S01#insulin": 2.79,
        "S01#water": 1829.2,
        "S01#food": 5487.5,
        "S02#insulin": 1.49,
        "S02#water": 1979.17,
        "S02#food": 4937.5,
        "S03#insulin": 39.70,
        "S03#water": 370,
        "S03#food": 910,
        "S04#insulin": 40.00,
        "S04#water": 987.5,
        "S04#food": 2962.5,
        "S05#insulin": 3.55,
        "S05#water": 2955,
        "S05#food": 4865,
    }
    for key, qty in expected.items():
        assert inv[key]["last_reported_qty"] == pytest.approx(qty, abs=TOL), key
        assert inv[key]["sim_hour"] == 9
    for site in ("S02", "S04"):
        for supply in ("water", "food", "insulin"):
            r = inv[f"{site}#{supply}"]
            assert r["report_age_h"] == 7 and r["data_status"] == "stale" and r["last_report_hour"] == 2
    for site in ("S01", "S03", "S05"):
        assert inv[f"{site}#insulin"]["data_status"] == "live"
    assert inv["S01#insulin"]["people_served"] == 500
    truth9 = {
        (t["site_id"], t["supply_id"]): t for t in store.get_jsonl(truth_key(DEMO)) if t["sim_hour"] == 9
    }
    assert truth9[("S04", "insulin")]["qty"] == pytest.approx(20.06, abs=TOL)
    assert all(t["unmet"] == 0 for t in truth9.values())
    sites = {s["site_id"]: s for s in store.query_pk(settings.TABLE_SITES, DEMO)}
    assert sites["S01"]["people_served"] == 500


def test_step_in_chunks_equals_one_step():
    run.reset(DEMO)
    run.step(DEMO, 4)
    run.step(DEMO, 9)
    chunked = store.get_object(truth_key(DEMO))
    run.reset(DEMO)
    run.step(DEMO, 9)
    assert store.get_object(truth_key(DEMO)) == chunked


def test_step_rules():
    run.reset(DEMO)
    run.step(DEMO, 9)
    with pytest.raises(ValueError):
        run.step(DEMO, 3)
    with pytest.raises(ValueError):
        run.step(DEMO, 73)
    assert run.step(DEMO, 9) == []
    assert run.current_hour(DEMO) == 9


def test_apply_transfers_moves_true_stock():
    run.reset(DEMO)
    run.step(DEMO, 9)
    run.apply_transfers(
        DEMO, [{"source_site_id": "S03", "dest_site_id": "S02", "supply_id": "insulin", "qty": 6}]
    )
    run.step(DEMO, 10)
    t10 = {(t["site_id"], t["supply_id"]): t for t in store.get_jsonl(truth_key(DEMO)) if t["sim_hour"] == 10}
    # S03 is live: 39.70 - 6 - one hour of burn
    assert t10[("S03", "insulin")]["qty"] == pytest.approx(39.70 - 6 - 80 * 0.01 / 24, abs=TOL)
