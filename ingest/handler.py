"""Ingest: raw hourly reports -> clean CSV + inventory rows (report fields only)."""

from __future__ import annotations

import csv
import io

from lantern_core import ids, store
from lantern_core.config import settings
from lantern_core.schemas import InventoryState, Report, status_for_age

CSV_COLUMNS = ["scenario_id", "sim_hour", "site_id", "supply_id", "qty", "people_served"]
REPORT_FIELDS = (
    "scenario_id",
    "site_supply",
    "site_id",
    "supply_id",
    "sim_hour",
    "last_reported_qty",
    "last_report_hour",
    "report_age_h",
    "data_status",
    "people_served",
    "updated_at",
)


def reports_key(scenario_id: str, sim_hour: int) -> str:
    return f"raw/scenarios/{scenario_id}/reports/h{int(sim_hour):03d}.jsonl"


def clean_key(scenario_id: str) -> str:
    return f"clean/scenarios/{scenario_id}/reports.csv"


def _csv_rows(reports: list[Report], header: bool) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if header:
        w.writerow(CSV_COLUMNS)
    for r in reports:
        w.writerow([r.scenario_id, r.sim_hour, r.site_id, r.supply_id, r.qty, r.people_served])
    return buf.getvalue()


def _append_csv(scenario_id: str, reports: list[Report], reset: bool) -> None:
    key = clean_key(scenario_id)
    existing = None if reset else store.get_text(key)
    text = (existing if existing else _csv_rows([], header=True)) + _csv_rows(reports, header=False)
    store.put_object(key, text, content_type="text/csv")


def _report_row(report: Report, existing: dict | None) -> dict:
    row = dict(existing or {})
    row.update(
        {
            "scenario_id": report.scenario_id,
            "site_supply": ids.site_supply(report.site_id, report.supply_id),
            "site_id": report.site_id,
            "supply_id": report.supply_id,
            "sim_hour": report.sim_hour,
            "last_reported_qty": report.qty,
            "last_report_hour": report.sim_hour,
            "report_age_h": 0,
            "data_status": "live",
            "people_served": report.people_served,
            "updated_at": settings.sim_hour_to_iso(report.sim_hour),
        }
    )
    return row


def process_hour(scenario_id: str, sim_hour: int, reset: bool = False) -> int:
    """Ingest reports/hNNN.jsonl. Silent rows get sim_hour and report_age_h updated.

    Writes report fields only and keeps any estimate fields already on the row. Returns rows written.
    """
    reports = [Report.model_validate(r) for r in store.get_jsonl(reports_key(scenario_id, sim_hour))]
    _append_csv(scenario_id, reports, reset)

    existing = {} if reset else {r["site_supply"]: r for r in store.query_pk(settings.TABLE_INVENTORY, scenario_id)}
    rows: dict[str, dict] = {}
    for rep in reports:
        key = ids.site_supply(rep.site_id, rep.supply_id)
        rows[key] = _report_row(rep, existing.get(key))
    for key, row in existing.items():
        if key in rows:
            continue
        age = int(sim_hour) - int(row["last_report_hour"])
        rows[key] = {
            **row,
            "sim_hour": int(sim_hour),
            "report_age_h": age,
            "data_status": status_for_age(age),
            "updated_at": settings.sim_hour_to_iso(sim_hour),
        }
    for row in rows.values():
        InventoryState.model_validate(row)
    store.batch_put(settings.TABLE_INVENTORY, list(rows.values()))
    return len(rows)


def ingest_report(report: Report) -> None:
    """Ingest one report outside the hourly feed (a confirmed field report)."""
    key = ids.site_supply(report.site_id, report.supply_id)
    existing = store.get_item(settings.TABLE_INVENTORY, report.scenario_id, key)
    row = _report_row(report, existing)
    InventoryState.model_validate(row)
    _append_csv(report.scenario_id, [report], reset=False)
    store.put_item(settings.TABLE_INVENTORY, row)


def handler(event: dict, context=None) -> dict:
    n = process_hour(event["scenario_id"], int(event["sim_hour"]), bool(event.get("reset", False)))
    return {"rows": n}
