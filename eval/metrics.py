"""Metric definitions (contract 2.9). Used by evaluation and the proof chart."""

from __future__ import annotations

from lantern_core.config import settings


def shortage_hours(truth_rows: list[dict]) -> int:
    """(site, supply, hour) cells where true stock is 0 and demand is above 0."""
    return sum(1 for t in truth_rows if float(t["qty"]) <= 0 and float(t["demand"]) > 0)


def unmet_demand_units(truth_rows: list[dict]) -> float:
    return round(sum(float(t["unmet"]) for t in truth_rows), 2)


def reserve_qty(supply_id: str, people_served: float) -> float:
    burn = float(people_served) * settings.usage_per_h(supply_id)
    return settings.reserve_hours(supply_id) * burn


def is_unsafe(true_source_qty: float, qty: float, supply_id: str, people_served: float) -> bool:
    """True when executing the transfer on the true stock leaves the source below its reserve."""
    return true_source_qty - float(qty) < reserve_qty(supply_id, people_served)


def interval_hit(true_qty: float, p05: float, p95: float) -> bool:
    return float(p05) <= float(true_qty) <= float(p95)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)
