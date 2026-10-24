"""Metric definitions (M2 doc, Phase 2). OWNER: M2.  DRAFT by M3 for M2 review.

shortage_hours       (site, supply, hour) where true stock = 0 and demand > 0  (counted by World)
unmet_demand_units   demand not served, summed                                 (counted by World)
unsafe transfer      one that, on TRUE stock, leaves the source below its reserve
                     (reserve = GATE reserve hours x normal burn), counting earlier
                     draws on the same source in the same plan
"""

from __future__ import annotations

from gate.rules import reserve_hours
from lantern_core.schemas import SUPPLIES, Transfer
from simulator.world import World


def unsafe_flags(world: World, transfers: list[Transfer]) -> list[bool]:
    drawn: dict[tuple[str, str], float] = {}
    flags = []
    for t in sorted(transfers, key=lambda t: t.priority_rank):
        key = (t.source_site_id, t.supply_id)
        drawn[key] = drawn.get(key, 0.0) + t.qty
        site = world.site(t.source_site_id)
        burn = world.people(t.source_site_id) * SUPPLIES[t.supply_id].usage_per_person_per_day / 24
        if t.supply_id not in {"water", "food", "insulin"} or site is None:
            flags.append(False)
            continue
        reserve = reserve_hours(SUPPLIES[t.supply_id].critical) * burn
        flags.append(world.stock[t.source_site_id][t.supply_id] - drawn[key] < reserve)
    return flags
