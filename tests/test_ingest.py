from ingest.handler import REPORT_FIELDS, clean_key, ingest_report, process_hour, reports_key
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import InventoryState, Report

SID = "ingest_test"


def _put_reports(h, rows):
    store.put_jsonl(
        reports_key(SID, h),
        [{"scenario_id": SID, "sim_hour": h, "site_id": s, "supply_id": "water", "qty": q, "people_served": 100} for s, q in rows],
    )


def _rows():
    return {r["site_supply"]: r for r in store.query_pk(settings.TABLE_INVENTORY, SID)}


def test_silent_sites_age_and_only_report_fields_written():
    _put_reports(0, [("S01", 100), ("S02", 50)])
    assert process_hour(SID, 0, reset=True) == 2
    rows = _rows()
    assert set(rows) == {"S01#water", "S02#water"}
    for r in rows.values():
        InventoryState.model_validate(r)
        assert set(r) <= set(REPORT_FIELDS)
        assert r["report_age_h"] == 0 and r["data_status"] == "live"

    # an engine writes estimate fields; ingest must keep them
    est = {**rows["S02#water"], "burn_rate_per_h": 1.5, "est_qty_p50": 40.0}
    store.put_item(settings.TABLE_INVENTORY, est)

    for h in (1, 2, 3):
        _put_reports(h, [("S01", 100 - h)])
        process_hour(SID, h)
        rows = _rows()
        assert rows["S01#water"]["report_age_h"] == 0
        assert rows["S01#water"]["last_reported_qty"] == 100 - h
        assert rows["S02#water"]["sim_hour"] == h
        assert rows["S02#water"]["report_age_h"] == h
        assert rows["S02#water"]["data_status"] == "stale"
        assert rows["S02#water"]["last_report_hour"] == 0
        assert rows["S02#water"]["last_reported_qty"] == 50
        assert rows["S02#water"]["est_qty_p50"] == 40.0

    csv_lines = store.get_text(clean_key(SID)).splitlines()
    assert csv_lines[0] == "scenario_id,sim_hour,site_id,supply_id,qty,people_served"
    assert len(csv_lines) == 1 + 2 + 3


def test_missing_hour_file_ages_everything():
    _put_reports(0, [("S01", 10)])
    process_hour(SID, 0, reset=True)
    process_hour(SID, 1)
    assert _rows()["S01#water"]["report_age_h"] == 1


def test_ingest_report_makes_row_live():
    _put_reports(0, [("S01", 10)])
    process_hour(SID, 0, reset=True)
    for h in range(1, 5):
        process_hour(SID, h)
    ingest_report(Report(scenario_id=SID, sim_hour=4, site_id="S01", supply_id="water", qty=7, people_served=100))
    row = _rows()["S01#water"]
    assert row["report_age_h"] == 0 and row["last_reported_qty"] == 7 and row["data_status"] == "live"
    process_hour(SID, 5)
    assert _rows()["S01#water"]["report_age_h"] == 1
