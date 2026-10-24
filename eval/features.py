"""Build clean/training/features.csv (08_dataset.md columns; stock_qty = estimated p50)."""

from __future__ import annotations

import argparse
import csv
import io

from engine.estimator import estimate_row
from lantern_core import ids, store
from lantern_core.config import SUPPLY_ORDER, settings
from simulator.generator import (
    HORIZON_H,
    build,
    initial_truth,
    reports_for_hour,
    step_truth,
    test_ids,
    train_ids,
)

FEATURE_COLUMNS = [
    "scenario_id",
    "hazard",
    "sim_hour",
    "site_id",
    "site_type",
    "supply_id",
    "people_served",
    "temp_c",
    "hazard_level",
    "stock_qty",
    "burn_rate_per_h",
    "report_age_h",
    "target_tts_h",
]


def _target_tts(truth: dict[tuple[int, str, str], float], hour: int, site: str, supply: str, horizon: int) -> float:
    for t in range(hour, horizon + 1):
        if truth.get((t, site, supply), 0.0) <= 0:
            return float(t - hour)
    return float(settings.PLAN_HORIZON_H)


def rows_for_scenario(scenario_id: str) -> list[dict]:
    spec = build(scenario_id)
    weather = {w["sim_hour"]: w for w in spec.weather}
    types = {s["site_id"]: s["site_type"] for s in spec.sites}
    truth_map, _ = initial_truth(spec)
    stock: dict[tuple[int, str, str], float] = {}
    last_report: dict[tuple[str, str], tuple[int, float, int]] = {}
    snapshots: list[tuple[int, dict[tuple[str, str], tuple[int, float, int]]]] = []

    for h in range(0, spec.horizon_h + 1):
        if h > 0:
            truth_map, _, _ = step_truth(spec, h, truth_map)
        for sid in spec.site_ids:
            for supply in SUPPLY_ORDER:
                stock[(h, sid, supply)] = truth_map[ids.site_supply(sid, supply)]
        for r in reports_for_hour(spec, h, truth_map):
            last_report[(r["site_id"], r["supply_id"])] = (h, float(r["qty"]), int(r["people_served"]))
        if h < HORIZON_H:
            snapshots.append((h, dict(last_report)))

    out = []
    for h, reports in snapshots:
        w = weather.get(h, {"temp_c": 0.0, "hazard_level": 0})
        for i, site in enumerate(spec.sites):
            sid = site["site_id"]
            people = int(spec.people[h, i])
            for supply in SUPPLY_ORDER:
                key = (sid, supply)
                if key not in reports:
                    continue
                last_h, qty, people_r = reports[key]
                age = h - last_h
                row = estimate_row(
                    {
                        "scenario_id": scenario_id,
                        "site_supply": ids.site_supply(sid, supply),
                        "site_id": sid,
                        "supply_id": supply,
                        "sim_hour": h,
                        "last_reported_qty": qty,
                        "last_report_hour": last_h,
                        "report_age_h": age,
                        "data_status": "live" if age < 1 else "stale",
                        "people_served": people_r if age == 0 else people,
                    }
                )
                out.append(
                    {
                        "scenario_id": scenario_id,
                        "hazard": spec.hazard,
                        "sim_hour": h,
                        "site_id": sid,
                        "site_type": types[sid],
                        "supply_id": supply,
                        "people_served": people,
                        "temp_c": w["temp_c"],
                        "hazard_level": w["hazard_level"],
                        "stock_qty": round(row["est_qty_p50"], 4),
                        "burn_rate_per_h": round(row["burn_rate_per_h"], 6),
                        "report_age_h": age,
                        "target_tts_h": _target_tts(stock, h, sid, supply, spec.horizon_h),
                    }
                )
    return out


def write_features(scenario_ids: list[str], key: str = "clean/training/features.csv") -> int:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FEATURE_COLUMNS, lineterminator="\n")
    w.writeheader()
    n = 0
    for sid in scenario_ids:
        for row in rows_for_scenario(sid):
            w.writerow({c: row[c] for c in FEATURE_COLUMNS})
            n += 1
    store.put_object(key, buf.getvalue(), content_type="text/csv")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-train", type=int, default=200, help="train scenarios (test is never shrunk)")
    args = ap.parse_args()
    ids_ = train_ids(args.n_train) + test_ids()
    n = write_features(ids_)
    print(f"features.csv: {n} rows from {len(ids_)} scenarios ({settings.LANTERN_MODE} store)")


if __name__ == "__main__":
    main()
