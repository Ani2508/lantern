"""State estimate for stale inventory (contract 2.8, v1.2 formulas). Never reads truth."""

from __future__ import annotations

from lantern_core.config import Settings
from lantern_core.config import settings as default_settings


def heuristic_tts(qty: float, burn: float, horizon: float) -> float:
    if burn <= 0:
        return float(horizon)
    return min(float(horizon), max(0.0, qty) / burn)


def estimate_row(row: dict, s: Settings = default_settings) -> dict:
    d = dict(row)
    burn = float(d["people_served"]) * s.usage_per_h(d["supply_id"])
    age = float(d["report_age_h"])
    q = float(d["last_reported_qty"])
    p50 = max(0.0, q - burn * age)
    sigma = max(s.STALE_SIGMA_FRAC * burn * age, s.STALE_QTY_FRAC * q * age)
    p05 = max(0.0, p50 - s.Z_90 * sigma)
    p95 = p50 + s.Z_90 * sigma
    h = s.PLAN_HORIZON_H
    d.update(
        {
            "burn_rate_per_h": burn,
            "est_qty_p05": p05,
            "est_qty_p50": p50,
            "est_qty_p95": p95,
            "tts_p05_h": heuristic_tts(p05, burn, h),
            "tts_p50_h": heuristic_tts(p50, burn, h),
            "tts_p95_h": heuristic_tts(p95, burn, h),
        }
    )
    return d


def estimate(rows: list, s: Settings = default_settings) -> list[dict]:
    """Fill burn_rate_per_h, est_qty_p05/p50/p95 and the heuristic tts_* on each inventory row."""
    return [estimate_row(r.model_dump() if hasattr(r, "model_dump") else r, s) for r in rows]
