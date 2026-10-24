"""The outage world: truth stock, demand, hazards and who reports. OWNER: M2.
DRAFT by M3 for M2 review.

A World is one scenario, stepped hour by hour. It knows the TRUE stock (used
only for evaluation and training targets) and produces the REPORTS sites send
(the only thing the engine sees). Settings follow the Dataset doc section 3/4:
train and test scenarios differ on purpose so the forecaster can't memorise.

    w = World("eval_wildfire_l40_0007")
    for h in range(w.hours):
        reports = w.reports()          # what sites send this hour
        ...                            # ingest, plan, w.transfer(...)
        w.advance()                    # demand drains true stock
"""

from __future__ import annotations

import math
import zlib
from dataclasses import dataclass

import numpy as np

from engine.geo import distance_km
from lantern_core.schemas import SITE_SUPPLIES, SUPPLIES

BASE_SITES = [
    ("S01", "Shelter A", "shelter", 38.5576, -121.5000, 300),
    ("S02", "Shelter B", "shelter", 38.5400, -121.4500, 250),
    ("S03", "Riverside Clinic", "clinic", 38.4800, -121.4700, 80),
    ("S04", "Central Pharmacy", "pharmacy", 38.5000, -121.5000, 150),
    ("S05", "County Food Bank", "food_bank", 38.4500, -121.5300, 120),
]

# Dataset doc section 3: train vs test dynamics
PROFILE = {
    "train": dict(evac=(0.10, 0.40), mult=(1.0, 1.3), noise=0.10, panic_p=0.10, flaky=False, dark=(0, 3)),
    "test": dict(evac=(0.30, 0.80), mult=(1.2, 1.6), noise=0.15, panic_p=0.40, flaky=True, dark=(0, 3)),
    "eval": dict(evac=(0.20, 0.60), mult=(1.1, 1.4), noise=0.12, panic_p=0.25, flaky=False, dark=None),
}
HAZARD_DURATION = {"wildfire": (24, 48), "flood": (36, 72), "power_loss": (12, 36)}


@dataclass
class Spec:
    scenario_id: str
    kind: str  # train | test | eval
    hazard: str
    seed: int
    loss_pct: int | None


def parse(scenario_id: str) -> Spec:
    """train_<hazard>_<seed4> | test_<hazard>_<seed4> | eval_<hazard>_l<loss2>_<seed4>."""
    parts = scenario_id.split("_")
    kind = parts[0]
    if kind not in PROFILE:
        raise ValueError(f"not a generated scenario id: {scenario_id}")
    seed = int(parts[-1])
    if kind == "eval":
        loss = int(parts[-2][1:])
        hazard = "_".join(parts[1:-2])
    else:
        loss = None
        hazard = "_".join(parts[1:-1])
    if hazard not in HAZARD_DURATION:
        raise ValueError(f"unknown hazard in {scenario_id}")
    return Spec(scenario_id, kind, hazard, seed, loss)


def dark_count(loss_pct: int, n_sites: int = 5) -> int:
    return int(loss_pct * n_sites / 100 + 0.5)


class World:
    def __init__(self, scenario_id: str, hours: int = 72):
        self.spec = parse(scenario_id)
        self.id = scenario_id
        self.hours = hours
        self.hour = 0
        prof = PROFILE[self.spec.kind]
        rng = np.random.default_rng(zlib.crc32(scenario_id.encode()))
        self.rng = rng

        # sites: same mix as the demo, people jittered +-20%, positions jittered
        self.sites = []
        for sid, name, stype, lat, lon, ppl in BASE_SITES:
            self.sites.append(dict(site_id=sid, name=name, site_type=stype,
                                   lat=round(lat + rng.normal(0, 0.004), 4), lon=round(lon + rng.normal(0, 0.004), 4),
                                   people_served=int(ppl * rng.uniform(0.8, 1.2))))
        self.base_people = {s["site_id"]: s["people_served"] for s in self.sites}

        # hazard timing
        self.hazard_start = int(rng.integers(2, 7))
        lo, hi = HAZARD_DURATION[self.spec.hazard]
        self.hazard_end = self.hazard_start + int(rng.integers(lo, hi + 1))
        self.mult = float(rng.uniform(*prof["mult"]))
        self.noise = prof["noise"]

        # evacuees arrive at shelters one hour after the hazard starts
        self.evac_hour = self.hazard_start + 1
        self.evac = {s["site_id"]: int(s["people_served"] * rng.uniform(*prof["evac"]))
                     for s in self.sites if s["site_type"] == "shelter"}

        # outages from the hazard start
        n_sites = len(self.sites)
        if self.spec.kind == "eval":
            n_dark = dark_count(self.spec.loss_pct or 0, n_sites)
        else:
            n_dark = int(rng.integers(prof["dark"][0], prof["dark"][1] + 1))
            if self.spec.hazard == "power_loss":
                n_dark = min(n_sites - 1, n_dark + 1)
        ids = [s["site_id"] for s in self.sites]
        self.dark = set(rng.choice(ids, size=n_dark, replace=False).tolist()) if n_dark else set()
        if prof["flaky"]:
            # test only: staggered outages plus flaky sites skipping random hours
            self.dark_from = {sid: self.hazard_start + int(rng.integers(0, 6)) for sid in self.dark}
            self.flaky = {sid for sid in ids if sid not in self.dark and rng.random() < 0.4}
        else:
            self.dark_from = {sid: self.hazard_start for sid in self.dark}
            self.flaky = set()

        # panic buying at the pharmacy
        self.panic = None
        if rng.random() < prof["panic_p"]:
            self.panic = (self.hazard_start + 1, 6)  # (start hour, over hours)

        # starting stock (days of normal usage)
        self.stock: dict[str, dict[str, float]] = {}
        county = {sup: sum(self._base_burn(s, sup) for s in self.sites if s["site_type"] != "food_bank") * 24
                  for sup in SUPPLIES}
        for s in self.sites:
            st, sid = s["site_type"], s["site_id"]
            self.stock[sid] = {}
            for sup in SUPPLIES:
                daily = self._base_burn(s, sup) * 24
                if st == "food_bank":
                    days = rng.uniform(3, 5) if sup != "insulin" else 0
                    self.stock[sid][sup] = round(county[sup] * days, 2)
                elif sup == "insulin" and st == "pharmacy":
                    self.stock[sid][sup] = round(daily * rng.uniform(15, 30), 2)
                elif sup == "insulin" and st == "clinic":
                    self.stock[sid][sup] = round(daily * rng.uniform(5, 15), 2)
                elif sup in SITE_SUPPLIES[st]:
                    self.stock[sid][sup] = round(daily * rng.uniform(1.5, 4), 2)
                else:
                    self.stock[sid][sup] = 0.0
        if self.panic:
            ph = next(s for s in self.sites if s["site_type"] == "pharmacy")
            self.panic_qty = self.stock[ph["site_id"]]["insulin"] * rng.uniform(0.3, 0.6)
            self.panic_site = ph["site_id"]

        self.unmet_total = 0.0
        self.shortage_hours = 0
        self._last_people = dict(self.base_people)

    # --- helpers --------------------------------------------------------------
    @staticmethod
    def _base_burn(site: dict, supply: str) -> float:
        if supply not in SITE_SUPPLIES[site["site_type"]]:
            return 0.0
        return site["people_served"] * SUPPLIES[supply].usage_per_person_per_day / 24

    def people(self, site_id: str, hour: int | None = None) -> int:
        h = self.hour if hour is None else hour
        return self.base_people[site_id] + (self.evac.get(site_id, 0) if h >= self.evac_hour else 0)

    def in_hazard(self, hour: int | None = None) -> bool:
        h = self.hour if hour is None else hour
        return self.hazard_start <= h < self.hazard_end

    def hazard_level(self, hour: int | None = None) -> int:
        h = self.hour if hour is None else hour
        if not self.in_hazard(h):
            return 0
        frac = (h - self.hazard_start) / max(1, self.hazard_end - self.hazard_start)
        return 3 if frac < 0.5 else 2

    def temp_c(self, hour: int | None = None) -> float:
        h = self.hour if hour is None else hour
        base = 31 if self.spec.hazard == "wildfire" else 22
        return round(base + 5 * math.sin((h % 24 - 9) / 24 * 2 * math.pi), 1)

    def site(self, site_id: str) -> dict:
        return next(s for s in self.sites if s["site_id"] == site_id)

    def demand(self, site_id: str, supply: str) -> float:
        s = self.site(site_id)
        if supply not in SITE_SUPPLIES[s["site_type"]]:
            return 0.0
        d = self.people(site_id) * SUPPLIES[supply].usage_per_person_per_day / 24
        if self.in_hazard():
            d *= self.mult
        return d * float(self.rng.lognormal(0, self.noise))

    def is_reporting(self, site_id: str, hour: int | None = None) -> bool:
        h = self.hour if hour is None else hour
        if site_id in self.dark and h >= self.dark_from[site_id]:
            return False
        if site_id in self.flaky and self.in_hazard(h):
            return bool(self.rng.random() >= 0.3)
        return True

    # --- outputs --------------------------------------------------------------
    def site_rows(self, created_at: str) -> list[dict]:
        return [{"scenario_id": self.id, **s, "created_at": created_at} for s in self.sites]

    def events(self) -> list[dict]:
        ev = [{"sim_hour": self.hazard_start, "type": "hazard_start", "hazard": self.spec.hazard}]
        if self.dark:
            ev.append({"sim_hour": min(self.dark_from.values()), "type": "site_dark", "site_ids": sorted(self.dark)})
        for sid, n in self.evac.items():
            ev.append({"sim_hour": self.evac_hour, "type": "evacuee_arrival", "site_id": sid, "people": n})
        if self.panic:
            ev.append({"sim_hour": self.panic[0], "type": "demand_spike", "site_id": self.panic_site,
                       "supply_id": "insulin", "extra_qty": round(self.panic_qty, 2), "over_hours": self.panic[1]})
        return sorted(ev, key=lambda e: e["sim_hour"])

    def weather(self, hour: int | None = None) -> dict:
        h = self.hour if hour is None else hour
        return {"sim_hour": h, "temp_c": self.temp_c(h), "hazard_level": self.hazard_level(h)}

    def reports(self) -> list[dict]:
        out = []
        for s in self.sites:
            sid = s["site_id"]
            if not self.is_reporting(sid):
                continue
            for sup in SUPPLIES:
                out.append({"scenario_id": self.id, "sim_hour": self.hour, "site_id": sid, "supply_id": sup,
                            "qty": round(self.stock[sid][sup], 2), "people_served": self.people(sid)})
        return out

    def transfer(self, src: str, dst: str, supply: str, qty: float) -> float:
        """Move up to qty units now. Returns what actually moved (true stock limits it)."""
        moved = max(0.0, min(qty, self.stock[src][supply]))
        self.stock[src][supply] -= moved
        self.stock[dst][supply] += moved
        return moved

    def advance(self) -> list[dict]:
        """Drain one hour of demand. Returns truth rows for the hour just finished."""
        rows = []
        for s in self.sites:
            sid = s["site_id"]
            for sup in SUPPLIES:
                d = self.demand(sid, sup)
                if self.panic and sid == self.panic_site and sup == "insulin":
                    start, over = self.panic
                    if start <= self.hour < start + over:
                        d += self.panic_qty / over
                have = self.stock[sid][sup]
                unmet = max(0.0, d - have)
                if d > 0 and have <= 1e-9:
                    self.shortage_hours += 1
                self.unmet_total += unmet
                rows.append({"scenario_id": self.id, "sim_hour": self.hour, "site_id": sid, "supply_id": sup,
                             "qty": round(have, 2), "demand": round(d, 3), "unmet": round(unmet, 3)})
                self.stock[sid][sup] = max(0.0, have - d)
        self.hour += 1
        return rows

    def distance(self, a: str, b: str) -> float:
        sa, sb = self.site(a), self.site(b)
        return distance_km(sa["lat"], sa["lon"], sb["lat"], sb["lon"])
