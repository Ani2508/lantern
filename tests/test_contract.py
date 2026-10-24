import json

import pytest

from lantern_core.schemas import Event, Plan, Report, Site, TruthStock, Weather
from tests.conftest import FIXTURE_DIR


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sites_events_weather_validate():
    sites = [Site.model_validate(s) for s in json.loads((FIXTURE_DIR / "sites.json").read_text(encoding="utf-8"))]
    assert [s.site_id for s in sites] == ["S01", "S02", "S03", "S04", "S05"]
    events = [Event.model_validate(e) for e in json.loads((FIXTURE_DIR / "events.json").read_text(encoding="utf-8"))]
    assert {e.type for e in events} == {"hazard_start", "site_dark", "evacuee_arrival", "demand_spike"}
    weather = [Weather.model_validate(w) for w in _jsonl(FIXTURE_DIR / "weather.jsonl")]
    assert [w.sim_hour for w in weather] == list(range(10))


def test_reports_and_truth_validate():
    for h in range(10):
        rows = _jsonl(FIXTURE_DIR / "reports" / f"h{h:03d}.jsonl")
        assert rows, h
        for r in rows:
            Report.model_validate(r)
    truth = [TruthStock.model_validate(t) for t in _jsonl(FIXTURE_DIR / "truth" / "stock.jsonl")]
    assert len(truth) == 10 * 5 * 3


@pytest.mark.parametrize("name", ["plan_naive_h009.json", "plan_lantern_h009.json"])
def test_plan_fixtures_validate(name):
    path = FIXTURE_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not generated yet (python scripts/tasks.py regen-fixtures)")
    Plan.model_validate(json.loads(path.read_text(encoding="utf-8")))
