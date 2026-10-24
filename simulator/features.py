"""Build clean/training/features.csv (contract 2.9, v1.2). OWNER: M2.
DRAFT by M3 for M2 review.

For every train_* and test_* scenario, every 6 hours, every (site, supply) the
site consumes, one row of what the ENGINE would see at that hour:
    stock_qty      = estimated stock (estimator p50 from the last report and its age)
    report_age_h   = hours since that site last reported
    target_tts_h   = hours until TRUE stock first hits 0, capped at 72 (the label)
Worlds run 144 h so every target in the first 72 h is fully observed.

    python -m simulator.features --train 200 --test 60
"""

from __future__ import annotations

import argparse
import io

import pandas as pd

from engine.estimator import estimate_row
from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import scenario_id as make_id
from lantern_core.schemas import SITE_SUPPLIES, SUPPLIES, InventoryState
from simulator.world import World

COLUMNS = [
    "scenario_id", "hazard", "sim_hour", "site_id", "site_type", "supply_id", "people_served",
    "temp_c", "hazard_level", "stock_qty", "burn_rate_per_h", "report_age_h", "target_tts_h",
]
HAZARDS = ["wildfire", "flood", "power_loss"]


def scenario_rows(sid: str, every_h: int = 6, horizon: int = 72) -> list[dict]:
    w = World(sid, hours=horizon * 2)
    last: dict[tuple[str, str], tuple[float, int, int]] = {}  # (qty, hour, people)
    truth: dict[tuple[str, str], list[float]] = {}
    pending = []  # (hour, row-without-target, key)
    for h in range(w.hours):
        for r in w.reports():
            last[(r["site_id"], r["supply_id"])] = (r["qty"], h, r["people_served"])
        for s in w.sites:
            for sup in SUPPLIES:
                truth.setdefault((s["site_id"], sup), []).append(w.stock[s["site_id"]][sup])
        if h < horizon and h % every_h == 0:
            weather = w.weather()
            for s in w.sites:
                for sup in SITE_SUPPLIES[s["site_type"]]:
                    key = (s["site_id"], sup)
                    if key not in last:
                        continue
                    qty, rep_h, ppl = last[key]
                    inv = InventoryState(
                        scenario_id=sid, site_supply=f"{key[0]}#{sup}", site_id=key[0], supply_id=sup, sim_hour=h,
                        last_reported_qty=qty, last_report_hour=rep_h, report_age_h=h - rep_h,
                        data_status="live" if h == rep_h else "stale", people_served=ppl, updated_at="",
                    )
                    est = estimate_row(inv)
                    pending.append((h, key, {
                        "scenario_id": sid, "hazard": w.spec.hazard, "sim_hour": h, "site_id": key[0],
                        "site_type": s["site_type"], "supply_id": sup, "people_served": ppl,
                        "temp_c": weather["temp_c"], "hazard_level": weather["hazard_level"],
                        "stock_qty": round(est.est_qty_p50 or 0.0, 2),
                        "burn_rate_per_h": round(est.burn_rate_per_h or 0.0, 4),
                        "report_age_h": h - rep_h,
                    }))
        w.advance()
    rows = []
    for h, key, row in pending:
        series = truth[key]
        tts = float(horizon)
        for k in range(h, min(len(series), h + horizon)):
            if series[k] <= 1e-9:
                tts = float(k - h)
                break
        rows.append({**row, "target_tts_h": tts})
    return rows


def build(n_train: int = 200, n_test: int = 60) -> pd.DataFrame:
    rows: list[dict] = []
    for kind, n in (("train", n_train), ("test", n_test)):
        for i in range(n):
            rows.extend(scenario_rows(make_id(kind, HAZARDS[i % 3], i)))
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=200)
    ap.add_argument("--test", type=int, default=60)
    a = ap.parse_args()
    df = build(a.train, a.test)
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    store.put_object("clean/training/features.csv", buf.getvalue())
    print(f"features.csv: {len(df):,} rows from {a.train} train + {a.test} test scenarios ({settings.lantern_mode} mode)")


if __name__ == "__main__":
    main()
