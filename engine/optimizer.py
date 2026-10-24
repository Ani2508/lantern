"""Greedy transfer optimizer (extras/plans/03_demo_numbers.md section 4).

lantern: robust and gate-aware. Views worst-case stock (p05), keeps a reserve, caps each source at
         the gate's R4 review band and R3 size limit, and prefers live sources.
naive:   trusts last_reported_qty as if it were live, keeps no reserve, nearest source first.
"""

from __future__ import annotations

from lantern_core import ids
from lantern_core.config import SUPPLY_ORDER, settings
from lantern_core.geo import site_distance_km
from lantern_core.schemas import Transfer

_EPS = 1e-9


def _as_dict(x) -> dict:
    return x.model_dump() if hasattr(x, "model_dump") else dict(x)


def _burn(r: dict) -> float:
    b = r.get("burn_rate_per_h")
    return float(b) if b is not None else float(r["people_served"]) * settings.usage_per_h(r["supply_id"])


def propose(
    inventory: list,
    sites: list,
    mode: str,
    plan_id: str,
    session_draws: dict[tuple[str, str], dict] | None = None,
) -> list[Transfer]:
    if mode not in ("lantern", "naive"):
        raise ValueError(f"unknown optimizer mode {mode!r}")
    rows = {r["site_supply"]: r for r in (_as_dict(x) for x in inventory)}
    sites_by_id = {s["site_id"]: s for s in (_as_dict(x) for x in sites)}
    session_draws = session_draws or {}
    horizon = settings.PLAN_HORIZON_H

    view: dict[str, float] = {}
    for k, r in rows.items():
        view[k] = float(r["last_reported_qty"]) if mode == "naive" else float(r["est_qty_p05"])

    def need(k: str) -> float:
        return _burn(rows[k]) * horizon - view[k]

    dests = {k for k in rows if need(k) >= settings.MIN_TRANSFER_QTY[rows[k]["supply_id"]]}

    avail: dict[str, float] = {}
    size_cap: dict[str, float] = {}
    for k, r in rows.items():
        if k in dests:
            continue
        supply = r["supply_id"]
        if mode == "naive":
            avail[k] = float(r["last_reported_qty"])
            size_cap[k] = float("inf")
            continue
        p05 = float(r["est_qty_p05"])
        reserve = settings.reserve_hours(supply) * _burn(r)
        prior = session_draws.get((r["site_id"], supply), {})
        prior_draw = float(prior.get("draw", 0.0))
        p05_start = float(prior.get("p05_start", p05))
        band = settings.GATE_SESSION_REVIEW_FRAC * settings.GATE_SESSION_DRAW_FRAC * p05_start
        avail[k] = min(p05 - reserve - prior_draw, band - prior_draw - 0.01)
        size_cap[k] = settings.GATE_MAX_TRANSFER_FRAC * p05

    def source_order(dest_site: str, k: str):
        r = rows[k]
        dist = site_distance_km(sites_by_id, r["site_id"], dest_site)
        if mode == "naive":
            return (dist, r["site_id"])
        stale = float(r["report_age_h"]) > settings.GATE_STALE_REVIEW_H
        return (stale, dist, r["site_id"])

    def tts_view(k: str) -> float:
        b = _burn(rows[k])
        return view[k] / b if b > 0 else float("inf")

    transfers: list[Transfer] = []
    active = set(dests)
    while active and len(transfers) < settings.MAX_TRANSFERS_PER_PLAN:
        k = min(active, key=lambda x: (tts_view(x), rows[x]["site_id"], SUPPLY_ORDER.index(rows[x]["supply_id"])))
        r = rows[k]
        supply = r["supply_id"]
        min_qty, cap = settings.MIN_TRANSFER_QTY[supply], settings.TRANSFER_CAP[supply]
        if need(k) < min_qty:
            active.discard(k)
            continue
        sources = [
            s
            for s in avail
            if rows[s]["supply_id"] == supply and min(avail[s], size_cap[s]) >= min_qty - _EPS
        ]
        if not sources:
            active.discard(k)
            continue
        src = min(sources, key=lambda s: source_order(r["site_id"], s))
        qty = round(min(need(k), avail[src], size_cap[src], cap), 2)
        if qty < min_qty - _EPS:
            active.discard(k)
            continue
        n = len(transfers) + 1
        transfers.append(
            Transfer(
                transfer_id=ids.transfer_id(plan_id, n),
                plan_id=plan_id,
                source_site_id=rows[src]["site_id"],
                dest_site_id=r["site_id"],
                supply_id=supply,
                qty=qty,
                priority_rank=n,
                distance_km=site_distance_km(sites_by_id, rows[src]["site_id"], r["site_id"]),
            )
        )
        view[k] += qty
        avail[src] -= qty
    return transfers
