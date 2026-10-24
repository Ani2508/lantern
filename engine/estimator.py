"""State estimator: turns an old count into a range (contract 2.8, v1.2). OWNER: M3.

For each inventory row:
    burn  = people_served x usage_per_person_per_day / 24
    p50   = max(0, last_reported_qty - burn x age)
    sigma = max(STALE_SIGMA_FRAC x burn x age,                # usage uncertainty
                STALE_QTY_FRAC x last_reported_qty x age)  # v1.2: unseen events
    p05   = max(0, p50 - Z_90 x sigma)      p95 = p50 + Z_90 x sigma

Time-to-shortage (tts) here is the simple stock / burn fallback; the
forecaster replaces it when a trained model is available.
Nothing here ever reads truth/.
"""

from __future__ import annotations

from lantern_core.config import settings
from lantern_core.schemas import SUPPLIES, InventoryState


def burn_rate_per_h(row: InventoryState) -> float:
    return row.people_served * SUPPLIES[row.supply_id].usage_per_person_per_day / 24


def tts_hours(stock: float, burn: float) -> float:
    """Hours until stock hits 0, capped at the planning horizon."""
    if burn <= 0:
        return float(settings.plan_horizon_h)
    return min(float(settings.plan_horizon_h), max(0.0, stock / burn))


def estimate_row(row: InventoryState) -> InventoryState:
    burn = burn_rate_per_h(row)
    age = float(row.report_age_h)
    last = float(row.last_reported_qty)
    p50 = max(0.0, last - burn * age)
    sigma = max(settings.stale_sigma_frac * burn * age, settings.stale_qty_frac * last * age)
    p05 = max(0.0, p50 - settings.z_90 * sigma)
    p95 = p50 + settings.z_90 * sigma
    return row.model_copy(update={
        "burn_rate_per_h": burn,
        "est_qty_p05": p05,
        "est_qty_p50": p50,
        "est_qty_p95": p95,
        "tts_p05_h": tts_hours(p05, burn),
        "tts_p50_h": tts_hours(p50, burn),
        "tts_p95_h": tts_hours(p95, burn),
    })


def estimate(inventory: list[InventoryState]) -> list[InventoryState]:
    return [estimate_row(r) for r in inventory]
