"""Equal-split baseline (contract 2.7). OWNER: M2.

STATUS: starter. Pools reported stock per supply and shares it by people
served; moves stock from sites above their share to sites below it.
"""

from __future__ import annotations

from engine.geo import distance_km
from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import transfer_id
from lantern_core.schemas import InventoryState, Transfer


def propose(inventory: list[InventoryState], sim_hour: int, plan_id: str) -> list[Transfer]:
    if not inventory:
        return []
    sites = {s["site_id"]: s for s in store.query_pk(settings.table_sites, inventory[0].scenario_id)}
    transfers: list[Transfer] = []
    for supply in sorted({r.supply_id for r in inventory}):
        rows = [r for r in inventory if r.supply_id == supply]
        total = sum(r.last_reported_qty for r in rows)
        people = sum(r.people_served for r in rows) or 1
        delta = {r.site_id: r.last_reported_qty - total * r.people_served / people for r in rows}
        givers = sorted((s for s in delta if delta[s] > 0.5), key=lambda s: -delta[s])
        takers = sorted((s for s in delta if delta[s] < -0.5), key=lambda s: delta[s])
        for t in takers:
            need = -delta[t]
            for g in givers:
                if need < 0.5 or len(transfers) >= settings.max_transfers_per_plan:
                    break
                qty = round(min(need, delta[g]))
                if qty < 1:
                    continue
                delta[g] -= qty
                need -= qty
                a, b = sites.get(g, {}), sites.get(t, {})
                transfers.append(Transfer(
                    transfer_id=transfer_id(plan_id, len(transfers) + 1), plan_id=plan_id,
                    source_site_id=g, dest_site_id=t, supply_id=supply, qty=qty,
                    priority_rank=len(transfers) + 1,
                    distance_km=distance_km(a.get("lat", 0), a.get("lon", 0), b.get("lat", 0), b.get("lon", 0)),
                ))
    return transfers
