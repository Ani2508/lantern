"""Equal-split baseline: pool reported stock per supply and share it by people served."""

from __future__ import annotations

from lantern_core import ids
from lantern_core.config import SUPPLY_ORDER, settings
from lantern_core.geo import site_distance_km
from lantern_core.schemas import InventoryState, Transfer


def _as_dict(row) -> dict:
    return row.model_dump() if isinstance(row, InventoryState) else dict(row)


def propose(inventory: list, sim_hour: int, plan_id: str, sites: list | None = None) -> list[Transfer]:
    rows = [_as_dict(r) for r in inventory]
    sites_by_id = {(s["site_id"] if isinstance(s, dict) else s.site_id): (s if isinstance(s, dict) else s.model_dump()) for s in (sites or [])}
    transfers: list[Transfer] = []
    supplies = sorted({r["supply_id"] for r in rows}, key=lambda s: (not settings.is_critical(s), SUPPLY_ORDER.index(s)))
    for supply in supplies:
        group = [r for r in rows if r["supply_id"] == supply]
        pool = sum(float(r["last_reported_qty"]) for r in group)
        people = sum(int(r["people_served"]) for r in group)
        if pool <= 0 or people <= 0:
            continue
        gap = {r["site_id"]: float(r["last_reported_qty"]) - pool * int(r["people_served"]) / people for r in group}
        sources = sorted([s for s, g in gap.items() if g > 0], key=lambda s: (-gap[s], s))
        dests = sorted([s for s, g in gap.items() if g < 0], key=lambda s: (gap[s], s))
        cap, min_qty = settings.TRANSFER_CAP[supply], settings.MIN_TRANSFER_QTY[supply]
        for dst in dests:
            for src in sources:
                while -gap[dst] >= min_qty and gap[src] >= min_qty:
                    if len(transfers) >= settings.MAX_TRANSFERS_PER_PLAN:
                        return transfers
                    qty = round(min(-gap[dst], gap[src], cap), 2)
                    if qty < min_qty:
                        break
                    n = len(transfers) + 1
                    transfers.append(
                        Transfer(
                            transfer_id=ids.transfer_id(plan_id, n),
                            plan_id=plan_id,
                            source_site_id=src,
                            dest_site_id=dst,
                            supply_id=supply,
                            qty=qty,
                            priority_rank=n,
                            distance_km=site_distance_km(sites_by_id, src, dst),
                        )
                    )
                    gap[dst] += qty
                    gap[src] -= qty
    return transfers
