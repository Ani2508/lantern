"""The 8 data quality checks of extras/plans/08_dataset.md section 6."""

import json
import re

import pytest

from lantern_core import store
from lantern_core.config import SUPPLY_ORDER, settings
from lantern_core.schemas import Event, InventoryState, Report, Site, TruthStock, Weather
from simulator import generator, run
from simulator.generator import build, eval_ids, generate_files, test_ids, train_ids, truth_key
from tests.conftest import REPO_ROOT

DEMO = "wildfire_demo_01"
SAMPLE = [DEMO, *train_ids()[:3], *test_ids()[:3], "eval_wildfire_l40_0000", "eval_flood_l20_0001", "eval_power_loss_l70_0002"]


def _objects(prefix: str) -> dict[str, bytes]:
    return {k: store.get_object(k) for k in store.list_keys(prefix)}


# 1. schemas
@pytest.mark.parametrize("sid", SAMPLE)
def test_1_files_validate(sid):
    generate_files(sid)
    pre = f"raw/scenarios/{sid}"
    for s in store.get_json(f"{pre}/sites.json"):
        Site.model_validate(s)
    for e in store.get_json(f"{pre}/events.json"):
        Event.model_validate(e)
    weather = store.get_jsonl(f"{pre}/weather.jsonl")
    assert len(weather) == 73
    for w in weather:
        Weather.model_validate(w)
    for h in range(73):
        for r in store.get_jsonl(f"{pre}/reports/h{h:03d}.jsonl"):
            Report.model_validate(r)
    truth = store.get_jsonl(truth_key(sid))
    assert len(truth) == 73 * 5 * 3
    for t in truth:
        TruthStock.model_validate(t)


# 2. truth never negative, unmet consistent
@pytest.mark.parametrize("sid", SAMPLE)
def test_2_truth_non_negative_and_unmet_consistent(sid):
    spec = build(sid)
    generate_files(sid)
    truth = store.get_jsonl(truth_key(sid))
    prev = {}
    for t in truth:
        key = (t["site_id"], t["supply_id"])
        assert t["qty"] >= 0 and t["demand"] >= 0 and t["unmet"] >= 0
        assert t["unmet"] <= t["demand"] + 0.01
        if t["sim_hour"] > 0:
            q = prev[key]
            if t["supply_id"] == "insulin":
                q *= 1 - float(spec.spoil_per_h[t["sim_hour"]])
            available = q + spec.deliveries.get((t["sim_hour"], *key), 0.0)
            assert t["unmet"] == pytest.approx(max(0.0, t["demand"] - available), abs=0.02), (sid, t)
            if t["unmet"] > 0.01:
                assert t["qty"] <= 0.01
        prev[key] = t["qty"]


# 3. silent sites: no report lines after the outage hour, report_age_h grows by 1 each hour
@pytest.mark.parametrize("sid", [DEMO, "eval_wildfire_l40_0000", train_ids()[1], test_ids()[0]])
def test_3_silent_sites_age(sid):
    spec = build(sid)
    outage = spec.outage_hours()
    run.reset(sid)
    last_report = dict.fromkeys(spec.site_ids, 0)
    for h in range(1, 31):
        run.step(sid, h)
        reported = {r["site_id"] for r in store.get_jsonl(f"raw/scenarios/{sid}/reports/h{h:03d}.jsonl")}
        for s, oh in outage.items():
            if h > oh:
                assert s not in reported, (s, h)
        for s in reported:
            last_report[s] = h
        for row in store.query_pk(settings.TABLE_INVENTORY, sid):
            InventoryState.model_validate(row)
            assert row["sim_hour"] == h
            assert row["report_age_h"] == h - last_report[row["site_id"]], (row, h)


# 4. reproducibility
@pytest.mark.parametrize("sid", [DEMO, train_ids()[0], test_ids()[1], "eval_flood_l30_0003"])
def test_4_byte_identical(sid):
    generate_files(sid)
    first = {**_objects(f"raw/scenarios/{sid}/"), **_objects(f"truth/scenarios/{sid}/")}
    store.reset_memory()
    build.cache_clear()
    generate_files(sid)
    second = {**_objects(f"raw/scenarios/{sid}/"), **_objects(f"truth/scenarios/{sid}/")}
    assert first == second


# 5. no overlap between train, test and eval seeds
def test_5_disjoint_seeds():
    tr, te, ev = train_ids(), test_ids(), eval_ids()
    assert len(tr) == 200 and len(te) == 60 and len(ev) == 3 * 8 * 20
    assert not set(tr) & set(te)
    seed = lambda s: int(s.rsplit("_", 1)[1])  # noqa: E731
    assert not {seed(s) for s in tr} & {seed(s) for s in te}
    assert not {seed(s) for s in ev} & {seed(s) for s in tr}
    assert not {seed(s) for s in ev} & {seed(s) for s in te}
    hazards = [s.split("_", 1)[1].rsplit("_", 1)[0] for s in tr]
    assert (hazards.count("wildfire"), hazards.count("flood"), hazards.count("power_loss")) == (67, 67, 66)
    hazards = [s.split("_", 1)[1].rsplit("_", 1)[0] for s in te]
    assert hazards.count("wildfire") == hazards.count("flood") == hazards.count("power_loss") == 20


# 6. demo hour 9
def test_6_demo_hour9():
    run.reset(DEMO)
    run.step(DEMO, 9)
    row = store.get_item(settings.TABLE_INVENTORY, DEMO, "S04#insulin")
    assert row["last_report_hour"] == 2
    assert row["last_reported_qty"] == pytest.approx(40.0, abs=0.05)
    t9 = [t for t in store.get_jsonl(truth_key(DEMO)) if t["sim_hour"] == 9 and t["site_id"] == "S04" and t["supply_id"] == "insulin"]
    assert t9[0]["qty"] == pytest.approx(20.06, abs=0.05)


# 7. the engine never reads truth/
def test_7_engine_never_reads_truth():
    pattern = re.compile(r"truth/|truth_key|simulator\.generator|from simulator|import simulator")
    offenders = []
    for pkg in ("engine", "gate", "explain", "baselines"):
        for path in (REPO_ROOT / pkg).rglob("*.py"):
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, offenders


# 8. test-set dynamics differ from train
def test_8_test_dynamics():
    for sid in test_ids()[:6]:
        spec = build(sid)
        assert spec.sigma == 0.15
        assert 1.2 <= spec.hazard_mult <= 1.6
        base = {s["site_id"]: s["people_served"] for s in spec.sites}
        for e in spec.events:
            if e["type"] == "evacuee_arrival":
                assert 0.3 - 0.01 <= e["people"] / base[e["site_id"]] <= 0.8 + 0.01, (sid, e)
        flaky = [
            sid_
            for i, sid_ in enumerate(spec.site_ids)
            if sid_ not in spec.outage_hours() and not spec.reports_at[:, i].all()
        ]
        assert flaky, f"{sid} should have a flaky site"
        dark_events = [e for e in spec.events if e["type"] == "site_dark"]
        assert all(len(e["site_ids"]) == 1 for e in dark_events)  # staggered
    for sid in train_ids()[:6]:
        spec = build(sid)
        assert spec.sigma == 0.10
        assert 1.0 <= spec.hazard_mult <= 1.3
        base = {s["site_id"]: s["people_served"] for s in spec.sites}
        for e in spec.events:
            if e["type"] == "evacuee_arrival":
                assert 0.1 - 0.01 <= e["people"] / base[e["site_id"]] <= 0.4 + 0.01, (sid, e)
        assert all(spec.reports_at[:, i].all() for i, s in enumerate(spec.site_ids) if s not in spec.outage_hours())
        assert len([e for e in spec.events if e["type"] == "site_dark"]) <= 1


def test_spec_shapes_and_supply_order():
    spec = build("eval_wildfire_l40_0000")
    assert spec.demand.shape == (73, 5, len(SUPPLY_ORDER))
    assert spec.data_loss_pct == 40
    assert len(spec.outage_hours()) == 2
    same_world = build("eval_wildfire_l10_0000")
    assert same_world.initial == spec.initial
    strip = lambda sites: json.dumps([{k: v for k, v in s.items() if k != "scenario_id"} for s in sites])  # noqa: E731
    assert strip(same_world.sites) == strip(spec.sites)
    assert generator.build(DEMO).initial[("S01", "insulin")] == 4.5
