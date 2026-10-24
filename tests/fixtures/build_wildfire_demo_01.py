"""Builds the hand-made wildfire_demo_01 fixture from the numbers in extras/plans/03_demo_numbers.md.

Deliberately independent of simulator/generator.py, so test_sim_demo cross-checks the simulator.
Run: python tests/fixtures/build_wildfire_demo_01.py   (rewrites the data files, not the plan files)
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "wildfire_demo_01"
SCENARIO = "wildfire_demo_01"
START = "2026-11-07T08:00:00Z"
HOURS = range(0, 10)

SITES = [
    ("S01", "Shelter A", "shelter", 37.3000, -121.9000, 300),
    ("S02", "Shelter B", "shelter", 37.3100, -121.8800, 250),
    ("S03", "Riverside Clinic", "clinic", 37.3400, -121.9300, 80),
    ("S04", "Central Pharmacy", "pharmacy", 37.3050, -121.8900, 150),
    ("S05", "County Food Bank", "food_bank", 37.2800, -121.9400, 120),
]
USAGE = {"water": 1.0, "food": 3.0, "insulin": 0.01}
STOCK0 = {
    # 4.50, not 03's 4.27: S01 burns 0.125/h at 300 people (03 says 0.0125, a typo); 4.50 keeps h9 at 2.79
    "S01": {"water": 2000, "food": 6000, "insulin": 4.50},
    "S02": {"water": 2000, "food": 5000, "insulin": 1.70},
    "S03": {"water": 400, "food": 1000, "insulin": 40.00},
    "S04": {"water": 1000, "food": 3000, "insulin": 40.125},
    "S05": {"water": 3000, "food": 5000, "insulin": 4.00},
}
EVENTS = [
    {"sim_hour": 2, "type": "hazard_start", "hazard": "wildfire"},
    {"sim_hour": 2, "type": "site_dark", "site_ids": ["S02", "S04"]},
    {"sim_hour": 3, "type": "evacuee_arrival", "site_id": "S01", "people": 200},
    {"sim_hour": 3, "type": "demand_spike", "site_id": "S04", "supply_id": "insulin", "extra_qty": 19.5, "over_hours": 7},
]
WEATHER = {0: (24, 0), 1: (24, 0), 2: (30, 1), 3: (33, 2), 4: (33, 2)}
DARK = {"S02": 2, "S04": 2}


def people(site: str, base: int, h: int) -> int:
    return base + (200 if site == "S01" and h >= 3 else 0)


def demand(site: str, base: int, supply: str, h: int) -> float:
    if h == 0:
        return 0.0
    d = people(site, base, h) * USAGE[supply] / 24
    if site == "S04" and supply == "insulin" and 3 <= h <= 9:
        d += 19.5 / 7
    return d


def main() -> None:
    (OUT / "reports").mkdir(parents=True, exist_ok=True)
    (OUT / "truth").mkdir(parents=True, exist_ok=True)
    sites = [
        {
            "scenario_id": SCENARIO,
            "site_id": s,
            "name": n,
            "site_type": t,
            "lat": lat,
            "lon": lon,
            "people_served": p,
            "created_at": START,
        }
        for s, n, t, lat, lon, p in SITES
    ]
    (OUT / "sites.json").write_text(json.dumps(sites, indent=1) + "\n", encoding="utf-8")
    (OUT / "events.json").write_text(json.dumps(EVENTS, indent=1) + "\n", encoding="utf-8")
    (OUT / "initial_stock.json").write_text(json.dumps(STOCK0, indent=1) + "\n", encoding="utf-8")
    with (OUT / "weather.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for h in HOURS:
            temp, level = WEATHER.get(h, (35, 3))
            f.write(json.dumps({"sim_hour": h, "temp_c": temp, "hazard_level": level}) + "\n")

    stock = {s: dict(v) for s, v in STOCK0.items()}
    truth_lines = []
    for h in HOURS:
        lines = []
        for s, _n, _t, _lat, _lon, base in SITES:
            for supply in ("water", "food", "insulin"):
                d = demand(s, base, supply, h)
                stock[s][supply] = stock[s][supply] - d
                truth_lines.append(
                    {
                        "scenario_id": SCENARIO,
                        "sim_hour": h,
                        "site_id": s,
                        "supply_id": supply,
                        "qty": round(stock[s][supply], 2),
                        "demand": round(d, 2),
                        "unmet": 0.0,
                    }
                )
                if s in DARK and h > DARK[s]:
                    continue
                lines.append(
                    {
                        "scenario_id": SCENARIO,
                        "sim_hour": h,
                        "site_id": s,
                        "supply_id": supply,
                        "qty": round(stock[s][supply], 2),
                        "people_served": people(s, base, h),
                    }
                )
        with (OUT / "reports" / f"h{h:03d}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            f.writelines(json.dumps(r) + "\n" for r in lines)
    with (OUT / "truth" / "stock.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r) + "\n" for r in truth_lines)
    print(f"wrote fixture to {OUT}")


if __name__ == "__main__":
    main()
