"""Transfer optimizer with two modes. OWNER: M3.

Both modes share one greedy loop: most urgent need first, nearest source with
surplus, loads no bigger than settings.transfer_unit_cap. They differ only in
how they treat old data, which is the comparison the proof chart makes.

robust (planner "lantern")
    stock      = est_qty_p05 (worst case)
    sources    = only sites whose data is fresh enough not to need review
                 (report_age_h <= GATE_STALE_REVIEW_H)
    surplus    = p05 - max(reserve, own need over the horizon)
    caps       = each load <= GATE_MAX_TRANSFER_FRAC x source p05 and the
                 session total per source stays under the gate's review line
naive (planner "naive", the "trusts old data" AI)
    stock      = last_reported_qty, as if it were live
    sources    = any site, however old its data
    surplus    = stock - own need over the horizon (no safety reserve)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from engine.geo import distance_km
from lantern_core.config import settings
from lantern_core.ids import transfer_id
from lantern_core.schemas import SITE_SUPPLIES as DEST_SUPPLIES
from lantern_core.schemas import SUPPLIES, InventoryState, Transfer


@dataclass
class ProposeResult:
    transfers: list[Transfer]
    # (site_id, supply_id) -> believed surplus of stale sources robust mode skipped
    skipped_stale_sources: dict[tuple[str, str], float] = field(default_factory=dict)
    # (site_id, supply_id) -> need left unmet after planning
    unmet: dict[tuple[str, str], float] = field(default_factory=dict)


def reserve_qty(row: InventoryState) -> float:
    crit = SUPPLIES[row.supply_id].critical
    hours = settings.gate_source_reserve_h_critical if crit else settings.gate_source_reserve_h
    return hours * (row.burn_rate_per_h or 0.0)


def _round_load(supply: str, qty: float, up: bool) -> float:
    return float(math.ceil(qty) if up else math.floor(qty)) if qty > 0 else 0.0


def propose(
    inventory: list[InventoryState],
    sites: dict[str, dict],
    plan_id: str,
    mode: str,
) -> ProposeResult:
    """mode = "robust" | "naive". Inventory rows must already be estimated."""
    robust = mode == "robust"
    horizon = settings.plan_horizon_h

    def believed(r: InventoryState) -> float:
        return (r.est_qty_p05 or 0.0) if robust else r.last_reported_qty

    def own_need(r: InventoryState) -> float:
        return (r.burn_rate_per_h or 0.0) * horizon

    # --- needs -------------------------------------------------------------
    needs = []  # (urgency_h, site_id, supply_id, qty)
    for r in inventory:
        stype = sites.get(r.site_id, {}).get("site_type", "shelter")
        if r.supply_id not in DEST_SUPPLIES.get(stype, set()):
            continue
        burn = r.burn_rate_per_h or 0.0
        if burn <= 0:
            continue
        stock = believed(r)
        need = own_need(r) - stock
        if need >= 1:
            needs.append((stock / burn, r.site_id, r.supply_id, float(math.ceil(need))))
    needs.sort()

    # --- sources -----------------------------------------------------------
    surplus: dict[tuple[str, str], float] = {}
    load_cap: dict[tuple[str, str], float] = {}
    session_cap: dict[tuple[str, str], float] = {}
    skipped: dict[tuple[str, str], float] = {}
    for r in inventory:
        key = (r.site_id, r.supply_id)
        stock = believed(r)
        if robust:
            spare = stock - max(reserve_qty(r), own_need(r))
            if r.report_age_h > settings.gate_stale_review_h:
                if spare > 0 or r.last_reported_qty - own_need(r) > 0:
                    skipped[key] = max(spare, r.last_reported_qty - own_need(r))
                continue
            p05 = r.est_qty_p05 or 0.0
            load_cap[key] = settings.gate_max_transfer_frac * p05
            session_cap[key] = settings.gate_session_review_frac * settings.gate_session_draw_frac * p05
        else:
            spare = stock - own_need(r)
            load_cap[key] = float("inf")
            session_cap[key] = float("inf")
        if spare >= 1:
            surplus[key] = spare

    # --- greedy ------------------------------------------------------------
    transfers: list[Transfer] = []
    drawn: dict[tuple[str, str], float] = {}
    unmet: dict[tuple[str, str], float] = {}
    for _, dest, supply, need in needs:
        d = sites.get(dest, {})
        candidates = sorted(
            (k for k in surplus if k[1] == supply and k[0] != dest and surplus[k] >= 1),
            key=lambda k: distance_km(d.get("lat", 0), d.get("lon", 0),
                                      sites.get(k[0], {}).get("lat", 0), sites.get(k[0], {}).get("lon", 0)),
        )
        for src in candidates:
            while need >= 1 and len(transfers) < settings.max_transfers_per_plan:
                room = min(
                    surplus[src],
                    load_cap[src],
                    session_cap[src] - drawn.get(src, 0.0),
                    settings.transfer_unit_cap.get(supply, float("inf")),
                )
                qty = min(need, _round_load(supply, room, up=False))
                if qty < 1:
                    break
                s = sites.get(src[0], {})
                transfers.append(Transfer(
                    transfer_id=transfer_id(plan_id, len(transfers) + 1),
                    plan_id=plan_id,
                    source_site_id=src[0],
                    dest_site_id=dest,
                    supply_id=supply,
                    qty=qty,
                    priority_rank=len(transfers) + 1,
                    distance_km=distance_km(s.get("lat", 0), s.get("lon", 0), d.get("lat", 0), d.get("lon", 0)),
                ))
                surplus[src] -= qty
                drawn[src] = drawn.get(src, 0.0) + qty
                need -= qty
            if need < 1:
                break
        if need >= 1:
            unmet[(dest, supply)] = need
    return ProposeResult(transfers=transfers, skipped_stale_sources=skipped, unmet=unmet)
