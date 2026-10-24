"""Builds the hand-tuned demo scenario `wildfire_demo_01` (contract 2.5).

OWNER: M2 (starter version, tune the numbers as needed and update the README).

Run:  python -m simulator.demo_fixture   -> writes tests/fixtures/wildfire_demo_01/
The story at hour 9:
  * S02 and S04 last reported at hour 2 (7 h old), 2 of 5 sites dark = 40%.
  * S01 jumped from 300 to 500 people at hour 3.
  * S04 last reported ~40 insulin vials; panic buying took truth to ~20.
"""

from __future__ import annotations

import json
from pathlib import Path

from lantern_core.ids import iso, sim_time
from lantern_core.schemas import SUPPLIES

SCENARIO = "wildfire_demo_01"
HOURS = list(range(10))  # 0..9
SIM_START = "2026-11-07T08:00:00Z"
CREATED_AT = "2026-11-07T08:00:00Z"
DARK_FROM = 3  # first hour with no report from dark sites
DARK_SITES = {"S02", "S04"}

# Fictional county; positions are synthetic.
SITES = [
    {"site_id": "S01", "name": "Shelter A", "site_type": "shelter", "lat": 38.5576, "lon": -121.5000, "people_served": 300},
    {"site_id": "S02", "name": "Shelter B", "site_type": "shelter", "lat": 38.5400, "lon": -121.4500, "people_served": 250},
    {"site_id": "S03", "name": "Riverside Clinic", "site_type": "clinic", "lat": 38.4800, "lon": -121.4700, "people_served": 80},
    {"site_id": "S04", "name": "Central Pharmacy", "site_type": "pharmacy", "lat": 38.5000, "lon": -121.5000, "people_served": 150},
    {"site_id": "S05", "name": "County Food Bank", "site_type": "food_bank", "lat": 38.4500, "lon": -121.5300, "people_served": 120},
]

START_STOCK = {
    "S01": {"water": 900, "food": 2700, "insulin": 4},
    "S02": {"water": 750, "food": 2250, "insulin": 2},
    "S03": {"water": 240, "food": 720, "insulin": 10},
    "S04": {"water": 300, "food": 0, "insulin": 40.125},  # reports 40.0 at hour 2
    "S05": {"water": 3000, "food": 9000, "insulin": 0},
}

EVENTS = [
    {"sim_hour": 2, "type": "hazard_start", "hazard": "wildfire"},
    {"sim_hour": 2, "type": "site_dark", "site_ids": ["S02", "S04"]},
    {"sim_hour": 3, "type": "evacuee_arrival", "site_id": "S01", "people": 200},
    {"sim_hour": 3, "type": "demand_spike", "site_id": "S04", "supply_id": "insulin", "extra_qty": 20, "over_hours": 6},
]


def people_at(site_id: str, hour: int) -> int:
    base = next(s["people_served"] for s in SITES if s["site_id"] == site_id)
    if site_id == "S01" and hour >= 3:
        return base + 200
    return base


def weather(hour: int) -> dict:
    level = 0 if hour < 2 else (2 if hour < 5 else 3)
    return {"sim_hour": hour, "temp_c": round(24 + 1.5 * hour, 1), "hazard_level": level}


def build() -> dict[str, object]:
    """Return {relative_path: content} for every fixture file."""
    stock = {s: dict(v) for s, v in START_STOCK.items()}
    reports: dict[int, list[dict]] = {h: [] for h in HOURS}
    truth: list[dict] = []

    for h in HOURS:
        for site in SITES:
            sid = site["site_id"]
            ppl = people_at(sid, h)
            for sup, spec in SUPPLIES.items():
                qty = stock[sid][sup]
                demand = ppl * spec.usage_per_person_per_day / 24
                truth.append({
                    "scenario_id": SCENARIO, "sim_hour": h, "site_id": sid, "supply_id": sup,
                    "qty": round(qty, 2), "demand": round(demand, 3), "unmet": round(max(0.0, demand - qty), 3),
                })
                if not (sid in DARK_SITES and h >= DARK_FROM):
                    reports[h].append({
                        "scenario_id": SCENARIO, "sim_hour": h, "site_id": sid, "supply_id": sup,
                        "qty": round(qty, 2), "people_served": ppl,
                    })
                # advance truth to next hour
                drain = demand
                if sid == "S04" and sup == "insulin" and 3 <= h < 9:
                    drain += 20 / 6
                stock[sid][sup] = max(0.0, qty - drain)

    files: dict[str, object] = {
        "sites.json": [{"scenario_id": SCENARIO, **s, "created_at": CREATED_AT} for s in SITES],
        "events.json": EVENTS,
        "weather.jsonl": [weather(h) for h in HOURS],
        "truth/stock.jsonl": truth,
    }
    for h in HOURS:
        files[f"reports/h{h:03d}.jsonl"] = reports[h]
    return files


def write(out_dir: Path) -> None:
    for rel, content in build().items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith(".jsonl"):
            p.write_text("".join(json.dumps(r) + "\n" for r in content))  # type: ignore[union-attr]
        else:
            p.write_text(json.dumps(content, indent=1) + "\n")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / SCENARIO
    write(out)
    print(f"wrote fixture to {out}  (sim start {iso(sim_time(SIM_START, 0))})")
