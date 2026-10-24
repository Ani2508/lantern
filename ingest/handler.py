"""Ingest: reports -> clean CSV + lantern-dev-inventory report fields. OWNER: M2.

STATUS: starter (works for the demo fixture). Writes report fields only;
M3's estimate/forecast fields on existing rows are preserved.
"""

from __future__ import annotations

from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import iso, report_key, site_supply

REPORT_FIELDS = ("sim_hour", "last_reported_qty", "last_report_hour", "report_age_h", "data_status", "people_served")


def process_hour(scenario_id: str, sim_hour: int, reset: bool = False) -> int:
    """Ingest one hour. Returns the number of reports processed."""
    reports = store.get_jsonl(report_key(scenario_id, sim_hour))
    table = settings.table_inventory
    existing = {r["site_supply"]: r for r in store.query_pk(table, scenario_id)} if not reset else {}
    now = iso()

    # append to the clean CSV
    key = f"clean/scenarios/{scenario_id}/reports.csv"
    try:
        csv = store.get_object(key).decode()
    except KeyError:
        csv = ""
    if not csv:
        csv = "scenario_id,sim_hour,site_id,supply_id,qty,people_served\n"
    csv += "".join(
        f"{r['scenario_id']},{r['sim_hour']},{r['site_id']},{r['supply_id']},{r['qty']},{r['people_served']}\n"
        for r in reports
    )
    store.put_object(key, csv)

    seen = set()
    rows: list[dict] = []
    for r in reports:
        ss = site_supply(r["site_id"], r["supply_id"])
        seen.add(ss)
        row = dict(existing.get(ss, {}))
        row.update({
            "scenario_id": scenario_id, "site_supply": ss, "site_id": r["site_id"], "supply_id": r["supply_id"],
            "sim_hour": sim_hour, "last_reported_qty": r["qty"], "last_report_hour": sim_hour,
            "report_age_h": 0, "data_status": "live", "people_served": r["people_served"], "updated_at": now,
        })
        rows.append(row)

    # silent sites: age their last report
    for ss, row in existing.items():
        if ss in seen:
            continue
        row = dict(row)
        age = sim_hour - int(row["last_report_hour"])
        row.update({"sim_hour": sim_hour, "report_age_h": age,
                    "data_status": "live" if age < 1 else "stale", "updated_at": now})
        rows.append(row)

    store.batch_put(table, rows)
    return len(reports)


def lambda_handler(event, _context):
    """lantern-dev-ingest. event: {"scenario_id", "sim_hour"}"""
    return {"processed": process_hour(event["scenario_id"], int(event["sim_hour"]))}
