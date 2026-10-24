"""Deterministic scenario generator (extras/plans/08_dataset.md sections 2 and 3).

build(scenario_id) parses the hazard, loss level and seed from the id and returns a fully
precomputed ScenarioSpec (people, demand, deliveries, reporting pattern). wildfire_demo_01 loads
from tests/fixtures/wildfire_demo_01 and has no noise.

CLI: python -m simulator.generator --scenario train_wildfire_1000
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from lantern_core import ids, store
from lantern_core.config import DEMO_SCENARIO_ID, ROOT_DIR, SUPPLY_ORDER, settings

HORIZON_H = 72
FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures" / DEMO_SCENARIO_ID
REFERENCE_DIR = Path(__file__).resolve().parent / "reference"

SITE_TEMPLATE = [
    ("S01", "Shelter A", "shelter", 37.3000, -121.9000, 300),
    ("S02", "Shelter B", "shelter", 37.3100, -121.8800, 250),
    ("S03", "Riverside Clinic", "clinic", 37.3400, -121.9300, 80),
    ("S04", "Central Pharmacy", "pharmacy", 37.3050, -121.8900, 150),
    ("S05", "County Food Bank", "food_bank", 37.2800, -121.9400, 120),
]

# Hazard table (08 section 3): start hour range, duration range, peak hazard level range
HAZARDS = {
    "wildfire": {"start": (2, 6), "duration": (24, 48), "level": (2, 3), "temp": (26.0, 31.0), "temp_bump": 6.0},
    "flood": {"start": (2, 6), "duration": (36, 72), "level": (1, 3), "temp": (15.0, 22.0), "temp_bump": -2.0},
    "power_loss": {"start": (1, 4), "duration": (12, 36), "level": (1, 3), "temp": (18.0, 28.0), "temp_bump": 2.0},
}

# Train vs test dynamics (08 section 2); eval uses the train settings
DYNAMICS = {
    "train": {"wave": (0.10, 0.40), "mult": (1.0, 1.3), "sigma": 0.10, "spike_p": 0.10, "staggered": False},
    "test": {"wave": (0.30, 0.80), "mult": (1.2, 1.6), "sigma": 0.15, "spike_p": 0.40, "staggered": True},
}
FLOOD_WATER_EXTRA = 0.2
POWER_INSULIN_SPOIL_PER_H = 0.005
FLAKY_SKIP_P = 0.2

_KIND_CODE = {"train": 1, "test": 2, "eval": 3}
_HAZARD_CODE = {"wildfire": 1, "flood": 2, "power_loss": 3}
HAZARD_ORDER = ("wildfire", "flood", "power_loss")

# Disjoint seed ranges (this build's choice, 06 item 12)
TRAIN_SEEDS = range(1000, 1200)
TEST_SEEDS = range(2000, 2060)
EVAL_SEED_RANGE = range(0, 20)


def train_ids(n: int | None = None) -> list[str]:
    seeds = list(TRAIN_SEEDS)[: n or len(TRAIN_SEEDS)]
    return [ids.train_scenario_id(HAZARD_ORDER[(s - TRAIN_SEEDS.start) % 3], s) for s in seeds]


def test_ids() -> list[str]:
    return [ids.test_scenario_id(HAZARD_ORDER[(s - TEST_SEEDS.start) % 3], s) for s in TEST_SEEDS]


test_ids.__test__ = False


def eval_ids(n_seeds: int | None = None, levels: list[int] | None = None) -> list[str]:
    seeds = list(EVAL_SEED_RANGE)[: n_seeds or len(EVAL_SEED_RANGE)]
    levels = levels if levels is not None else settings.DATA_LOSS_LEVELS
    return [ids.eval_scenario_id(hz, lv, s) for hz in HAZARD_ORDER for lv in levels for s in seeds]


@dataclass
class ScenarioSpec:
    scenario_id: str
    kind: str
    hazard: str
    seed: int | None
    data_loss_pct: int
    sites: list[dict]
    initial: dict[tuple[str, str], float]
    events: list[dict]
    weather: list[dict]
    people: np.ndarray  # [H+1, n_sites] int
    demand: np.ndarray  # [H+1, n_sites, n_supplies]
    reports_at: np.ndarray  # [H+1, n_sites] bool
    deliveries: dict[tuple[int, str, str], float] = field(default_factory=dict)
    spoil_per_h: np.ndarray | None = None  # [H+1] fraction lost per hour (insulin only)
    cut_off: dict[str, tuple[int, int]] = field(default_factory=dict)  # site -> [start, end)
    hazard_start: int = 0
    hazard_end: int = 0
    sigma: float = 0.0
    hazard_mult: float = 1.0
    horizon_h: int = HORIZON_H

    @property
    def site_ids(self) -> list[str]:
        return [s["site_id"] for s in self.sites]

    def site_index(self, site_id: str) -> int:
        return self.site_ids.index(site_id)

    def outage_hours(self) -> dict[str, int]:
        """Hour of the last report for each site that goes dark (site_dark events)."""
        out = {}
        for e in self.events:
            if e["type"] == "site_dark":
                for s in e["site_ids"]:
                    out[s] = e["sim_hour"]
        return out


# --------------------------------------------------------------------------- helpers


def _supply_idx(supply_id: str) -> int:
    return SUPPLY_ORDER.index(supply_id)


def _usage_per_h(supply_id: str) -> float:
    return settings.usage_per_h(supply_id)


def _people_matrix(sites: list[dict], events: list[dict], horizon: int) -> np.ndarray:
    people = np.zeros((horizon + 1, len(sites)), dtype=np.int64)
    idx = {s["site_id"]: i for i, s in enumerate(sites)}
    for i, s in enumerate(sites):
        people[:, i] = s["people_served"]
    for e in events:
        if e["type"] == "evacuee_arrival":
            people[e["sim_hour"] :, idx[e["site_id"]]] += int(e["people"])
    return people


def _spike_matrix(sites: list[dict], events: list[dict], horizon: int) -> np.ndarray:
    extra = np.zeros((horizon + 1, len(sites), len(SUPPLY_ORDER)))
    idx = {s["site_id"]: i for i, s in enumerate(sites)}
    for e in events:
        if e["type"] == "demand_spike":
            per_h = float(e["extra_qty"]) / int(e["over_hours"])
            for h in range(e["sim_hour"], min(horizon, e["sim_hour"] + int(e["over_hours"]) - 1) + 1):
                extra[h, idx[e["site_id"]], _supply_idx(e["supply_id"])] += per_h
    return extra


def _reports_matrix(sites: list[dict], events: list[dict], horizon: int) -> np.ndarray:
    rep = np.ones((horizon + 1, len(sites)), dtype=bool)
    idx = {s["site_id"]: i for i, s in enumerate(sites)}
    for e in events:
        if e["type"] == "site_dark":
            for s in e["site_ids"]:
                rep[e["sim_hour"] + 1 :, idx[s]] = False
    return rep


def _site_dicts(scenario_id: str, people: list[int], coords: list[tuple[float, float]]) -> list[dict]:
    return [
        {
            "scenario_id": scenario_id,
            "site_id": sid,
            "name": name,
            "site_type": stype,
            "lat": round(coords[i][0], 4),
            "lon": round(coords[i][1], 4),
            "people_served": int(people[i]),
            "created_at": settings.SIM_START_TS,
        }
        for i, (sid, name, stype, _lat, _lon, _p) in enumerate(SITE_TEMPLATE)
    ]


# --------------------------------------------------------------------------- demo


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _build_demo() -> ScenarioSpec:
    sites = json.loads((FIXTURE_DIR / "sites.json").read_text(encoding="utf-8"))
    events = json.loads((FIXTURE_DIR / "events.json").read_text(encoding="utf-8"))
    weather_fx = {w["sim_hour"]: w for w in _read_jsonl(FIXTURE_DIR / "weather.jsonl")}
    last = weather_fx[max(weather_fx)]
    weather = [
        weather_fx.get(h, {"sim_hour": h, "temp_c": last["temp_c"], "hazard_level": last["hazard_level"]})
        for h in range(HORIZON_H + 1)
    ]
    stock0 = json.loads((FIXTURE_DIR / "initial_stock.json").read_text(encoding="utf-8"))
    initial = {(site, supply): float(q) for site, by_supply in stock0.items() for supply, q in by_supply.items()}
    people = _people_matrix(sites, events, HORIZON_H)
    demand = np.zeros((HORIZON_H + 1, len(sites), len(SUPPLY_ORDER)))
    for k, supply in enumerate(SUPPLY_ORDER):
        demand[1:, :, k] = people[1:, :] * _usage_per_h(supply)
    demand += _spike_matrix(sites, events, HORIZON_H)
    demand[0] = 0.0
    start = next(e["sim_hour"] for e in events if e["type"] == "hazard_start")
    return ScenarioSpec(
        scenario_id=DEMO_SCENARIO_ID,
        kind="demo",
        hazard="wildfire",
        seed=None,
        data_loss_pct=40,
        sites=sites,
        initial=initial,
        events=events,
        weather=weather,
        people=people,
        demand=demand,
        reports_at=_reports_matrix(sites, events, HORIZON_H),
        spoil_per_h=np.zeros(HORIZON_H + 1),
        hazard_start=start,
        hazard_end=HORIZON_H + 1,
    )


# --------------------------------------------------------------------------- generated scenarios


def _n_dark(loss_pct: int, n_sites: int = 5) -> int:
    return int(math.floor(loss_pct / 100 * n_sites + 0.5))


def _build_generated(scenario_id: str, kind: str, hazard: str, seed: int, loss: int | None) -> ScenarioSpec:
    dyn = DYNAMICS["test" if kind == "test" else "train"]
    hz = HAZARDS[hazard]
    rng = np.random.default_rng([_KIND_CODE[kind], _HAZARD_CODE[hazard], seed])
    n = len(SITE_TEMPLATE)
    H = HORIZON_H

    # sites
    people0 = [int(round(p * rng.uniform(0.8, 1.2))) for *_x, p in SITE_TEMPLATE]
    coords = [(lat + rng.uniform(-0.01, 0.01), lon + rng.uniform(-0.01, 0.01)) for _s, _n, _t, lat, lon, _p in SITE_TEMPLATE]
    sites = _site_dicts(scenario_id, people0, coords)

    # starting stock: 2-4 days of water and food; insulin concentrated at pharmacy and clinic
    initial: dict[tuple[str, str], float] = {}
    for i, s in enumerate(sites):
        for supply in ("water", "food"):
            days = rng.uniform(2.0, 4.0)
            initial[(s["site_id"], supply)] = round(people0[i] * settings.SUPPLIES[supply]["usage_per_person_per_day"] * days, 2)
        lo, hi = {"pharmacy": (30, 50), "clinic": (20, 40), "shelter": (0, 2), "food_bank": (0, 4)}[s["site_type"]]
        initial[(s["site_id"], "insulin")] = round(rng.uniform(lo, hi), 2)

    # hazard timing and intensity
    start = int(rng.integers(hz["start"][0], hz["start"][1] + 1))
    duration = int(rng.integers(hz["duration"][0], hz["duration"][1] + 1))
    end = min(H + 1, start + duration)
    peak = int(rng.integers(hz["level"][0], hz["level"][1] + 1))
    mult = float(rng.uniform(*dyn["mult"]))
    if loss is None:
        loss = int(rng.choice(settings.DATA_LOSS_LEVELS))

    events: list[dict] = [{"sim_hour": start, "type": "hazard_start", "hazard": hazard}]

    # evacuee waves to shelters
    shelters = [s["site_id"] for s in sites if s["site_type"] == "shelter"]
    wave_sites = shelters if hazard == "wildfire" else [shelters[int(rng.integers(0, len(shelters)))]]
    for sid in wave_sites:
        base = people0[[s["site_id"] for s in sites].index(sid)]
        h = min(H, start + int(rng.integers(1, 5)))
        events.append({"sim_hour": h, "type": "evacuee_arrival", "site_id": sid, "people": int(round(base * rng.uniform(*dyn["wave"])))})

    # panic buying at the pharmacy
    if rng.uniform() < dyn["spike_p"]:
        pharm = next(s["site_id"] for s in sites if s["site_type"] == "pharmacy")
        events.append(
            {
                "sim_hour": min(H, start + int(rng.integers(1, 4))),
                "type": "demand_spike",
                "site_id": pharm,
                "supply_id": "insulin",
                "extra_qty": round(initial[(pharm, "insulin")] * rng.uniform(0.3, 0.6), 2),
                "over_hours": int(rng.integers(4, 11)),
            }
        )

    # flood: one site cut off (deliveries and transfers blocked while the flood lasts)
    cut_off: dict[str, tuple[int, int]] = {}
    if hazard == "flood":
        cut_off[sites[int(rng.integers(0, n))]["site_id"]] = (start, end)

    # resupply deliveries to the food bank
    food_bank = next(s["site_id"] for s in sites if s["site_type"] == "food_bank")
    total_people = sum(people0)
    deliveries: dict[tuple[int, str, str], float] = {}
    for _ in range(int(rng.integers(1, 3))):
        h = int(rng.integers(18, 49))
        for supply in ("water", "food"):
            qty = round(total_people * settings.SUPPLIES[supply]["usage_per_person_per_day"] * rng.uniform(0.5, 1.0), 2)
            blocked = food_bank in cut_off and cut_off[food_bank][0] <= h < cut_off[food_bank][1]
            if not blocked:
                deliveries[(h, food_bank, supply)] = deliveries.get((h, food_bank, supply), 0.0) + qty
                events.append({"sim_hour": h, "type": "delivery", "site_id": food_bank, "supply_id": supply, "extra_qty": qty})

    # outages: separate stream so the same world is shared across loss levels
    orng = np.random.default_rng([_KIND_CODE[kind], _HAZARD_CODE[hazard], seed, loss, 7])
    order = [sites[i]["site_id"] for i in orng.permutation(n)]
    dark = order[: _n_dark(loss, n)]
    if dyn["staggered"]:
        for sid in dark:
            events.append({"sim_hour": min(H, start + int(orng.integers(0, 13))), "type": "site_dark", "site_ids": [sid]})
    elif dark:
        events.append({"sim_hour": start, "type": "site_dark", "site_ids": sorted(dark)})

    events.sort(key=lambda e: (e["sim_hour"], e["type"], e.get("site_id") or ""))

    # reporting matrix (+ flaky sites in test)
    reports_at = _reports_matrix(sites, events, H)
    if dyn["staggered"]:
        candidates = [s for s in order if s not in dark]
        n_flaky = min(len(candidates), int(orng.integers(1, 3)))
        for sid in candidates[:n_flaky]:
            i = [s["site_id"] for s in sites].index(sid)
            skip = orng.uniform(size=H + 1) < FLAKY_SKIP_P
            skip[0] = False
            reports_at[:, i] &= ~skip

    # weather
    base_temp = float(rng.uniform(*hz["temp"]))
    tnoise = rng.normal(0, 0.5, size=H + 1)
    weather = []
    for h in range(H + 1):
        active = start <= h < end
        temp = base_temp + 4.0 * math.sin(2 * math.pi * (h + 8 - 9) / 24) + (hz["temp_bump"] if active else 0.0) + tnoise[h]
        level = 0 if not active else (1 if h == start else peak)
        weather.append({"sim_hour": h, "temp_c": round(temp, 1), "hazard_level": level})

    # demand
    people = _people_matrix(sites, events, H)
    noise = rng.lognormal(0.0, dyn["sigma"], size=(H + 1, n, len(SUPPLY_ORDER)))
    demand = np.zeros((H + 1, n, len(SUPPLY_ORDER)))
    hmask = np.array([1.0 if start <= h < end else 0.0 for h in range(H + 1)])
    for k, supply in enumerate(SUPPLY_ORDER):
        m = 1.0 + (mult - 1.0) * hmask
        if hazard == "flood" and supply == "water":
            m = m + FLOOD_WATER_EXTRA * hmask
        demand[:, :, k] = people * _usage_per_h(supply) * m[:, None] * noise[:, :, k]
    demand += _spike_matrix(sites, events, H)
    demand[0] = 0.0

    spoil = np.zeros(H + 1)
    if hazard == "power_loss":
        spoil = POWER_INSULIN_SPOIL_PER_H * hmask

    return ScenarioSpec(
        scenario_id=scenario_id,
        kind=kind,
        hazard=hazard,
        seed=seed,
        data_loss_pct=loss,
        sites=sites,
        initial=initial,
        events=events,
        weather=weather,
        people=people,
        demand=demand,
        reports_at=reports_at,
        deliveries=deliveries,
        spoil_per_h=spoil,
        cut_off=cut_off,
        hazard_start=start,
        hazard_end=end,
        sigma=dyn["sigma"],
        hazard_mult=mult,
    )


@lru_cache(maxsize=64)
def build(scenario_id: str) -> ScenarioSpec:
    if scenario_id == DEMO_SCENARIO_ID:
        return _build_demo()
    p = ids.parse_scenario_id(scenario_id)
    return _build_generated(scenario_id, p["kind"], p["hazard"], p["seed"], p["data_loss_pct"])


# --------------------------------------------------------------------------- truth dynamics


def step_truth(
    spec: ScenarioSpec,
    h: int,
    prev: dict[str, float],
    transfers: list[dict] | None = None,
) -> tuple[dict[str, float], list[dict], list[dict]]:
    """Advance the true stock to hour h (08 section 3 order). prev maps site_supply -> qty.

    Returns (new truth map, truth lines, executed transfers with the qty actually moved).
    """
    base: dict[str, float] = {}
    for sid in spec.site_ids:
        for supply in SUPPLY_ORDER:
            key = ids.site_supply(sid, supply)
            q = prev[key]
            if supply == "insulin" and spec.spoil_per_h is not None:
                q *= 1.0 - float(spec.spoil_per_h[h])
            q += spec.deliveries.get((h, sid, supply), 0.0)
            base[key] = q

    out_used: dict[str, float] = {}
    inbound: dict[str, float] = {}
    executed: list[dict] = []
    for t in transfers or []:
        src, dst, supply = t["source_site_id"], t["dest_site_id"], t["supply_id"]
        if _is_cut_off(spec, src, h) or _is_cut_off(spec, dst, h):
            continue
        sk, dk = ids.site_supply(src, supply), ids.site_supply(dst, supply)
        free = max(0.0, base[sk] - out_used.get(sk, 0.0))
        sent = min(float(t["qty"]), free)
        if sent <= 0:
            continue
        out_used[sk] = out_used.get(sk, 0.0) + sent
        inbound[dk] = inbound.get(dk, 0.0) + sent
        executed.append({**t, "qty": sent})

    new: dict[str, float] = {}
    lines: list[dict] = []
    for i, sid in enumerate(spec.site_ids):
        for k, supply in enumerate(SUPPLY_ORDER):
            key = ids.site_supply(sid, supply)
            available = base[key] - out_used.get(key, 0.0) + inbound.get(key, 0.0)
            d = float(spec.demand[h, i, k])
            served = min(d, available)
            q = available - served
            new[key] = q
            lines.append(
                {
                    "scenario_id": spec.scenario_id,
                    "sim_hour": h,
                    "site_id": sid,
                    "supply_id": supply,
                    "qty": round(q, 2),
                    "demand": round(d, 2),
                    "unmet": round(d - served, 2),
                }
            )
    return new, lines, executed


def _is_cut_off(spec: ScenarioSpec, site_id: str, h: int) -> bool:
    w = spec.cut_off.get(site_id)
    return bool(w and w[0] <= h < w[1])


def initial_truth(spec: ScenarioSpec) -> tuple[dict[str, float], list[dict]]:
    truth = {ids.site_supply(s, sup): float(spec.initial[(s, sup)]) for s in spec.site_ids for sup in SUPPLY_ORDER}
    lines = [
        {
            "scenario_id": spec.scenario_id,
            "sim_hour": 0,
            "site_id": s,
            "supply_id": sup,
            "qty": round(truth[ids.site_supply(s, sup)], 2),
            "demand": 0.0,
            "unmet": 0.0,
        }
        for s in spec.site_ids
        for sup in SUPPLY_ORDER
    ]
    return truth, lines


def reports_for_hour(spec: ScenarioSpec, h: int, truth: dict[str, float]) -> list[dict]:
    out = []
    for i, sid in enumerate(spec.site_ids):
        if not spec.reports_at[h, i]:
            continue
        for supply in SUPPLY_ORDER:
            out.append(
                {
                    "scenario_id": spec.scenario_id,
                    "sim_hour": h,
                    "site_id": sid,
                    "supply_id": supply,
                    "qty": round(truth[ids.site_supply(sid, supply)], 2),
                    "people_served": int(spec.people[h, i]),
                }
            )
    return out


def sites_at_hour(spec: ScenarioSpec, h: int) -> list[dict]:
    return [{**s, "people_served": int(spec.people[h, i])} for i, s in enumerate(spec.sites)]


# --------------------------------------------------------------------------- file output


def raw_prefix(scenario_id: str) -> str:
    return f"raw/scenarios/{scenario_id}"


def truth_key(scenario_id: str) -> str:
    return f"truth/scenarios/{scenario_id}/stock.jsonl"


def write_static_files(spec: ScenarioSpec) -> None:
    """sites.json, events.json, weather.jsonl and the reference file."""
    pre = raw_prefix(spec.scenario_id)
    store.put_object(f"{pre}/sites.json", json.dumps(spec.sites, indent=1) + "\n", content_type="application/json")
    store.put_object(f"{pre}/events.json", json.dumps(spec.events, indent=1) + "\n", content_type="application/json")
    store.put_jsonl(f"{pre}/weather.jsonl", spec.weather)
    store.put_object(
        "raw/reference/water_guidance.json",
        (REFERENCE_DIR / "water_guidance.json").read_bytes(),
        content_type="application/json",
    )


def generate_files(scenario_id: str) -> list[str]:
    """Write a full 72-hour scenario (no transfers) into the store. Same id -> byte-identical files."""
    spec = build(scenario_id)
    write_static_files(spec)
    pre = raw_prefix(scenario_id)
    truth, lines = initial_truth(spec)
    all_lines = list(lines)
    store.put_jsonl(f"{pre}/reports/h000.jsonl", reports_for_hour(spec, 0, truth))
    for h in range(1, spec.horizon_h + 1):
        truth, lines, _ = step_truth(spec, h, truth)
        all_lines.extend(lines)
        store.put_jsonl(f"{pre}/reports/h{h:03d}.jsonl", reports_for_hour(spec, h, truth))
    store.put_jsonl(truth_key(scenario_id), all_lines)
    return [k for k in store.list_keys(pre + "/")] + [truth_key(scenario_id)]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default=DEMO_SCENARIO_ID)
    args = ap.parse_args()
    keys = generate_files(args.scenario)
    print(f"{args.scenario}: wrote {len(keys)} objects ({settings.LANTERN_MODE} store)")


if __name__ == "__main__":
    main()
