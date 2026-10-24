"""Scout visits: send someone to count where a count would change the plan (03 section 5)."""

from __future__ import annotations

from engine.estimator import heuristic_tts
from lantern_core import ids
from lantern_core.config import SUPPLY_ORDER, settings
from lantern_core.schemas import ScoutVisit


def _decision_relevant(r: dict) -> bool:
    supply = r["supply_id"]
    burn = float(r["burn_rate_per_h"])
    p05, p95 = float(r["est_qty_p05"]), float(r["est_qty_p95"])
    reserve = settings.reserve_hours(supply) * burn
    h = settings.PLAN_HORIZON_H
    # decided on the estimate quantities, so a forecaster model never changes who gets scouted
    tts05, tts95 = heuristic_tts(p05, burn, h), heuristic_tts(p95, burn, h)
    return (
        p05 < reserve <= p95
        or tts05 < settings.GATE_DEST_MIN_H <= tts95
        or (p95 - p05) >= settings.TRANSFER_CAP[supply]
    )


def voi_score(r: dict) -> float:
    p05, p50, p95 = float(r["est_qty_p05"]), float(r["est_qty_p50"]), float(r["est_qty_p95"])
    return (p95 - p05) / max(p50, 1.0) * (2.0 if settings.is_critical(r["supply_id"]) else 1.0)


def _range_text(p05: float, p95: float) -> tuple[str, str]:
    if p95 < 10:
        return f"{p05:.1f}", f"{p95:.1f}"
    return f"{p05:.0f}", f"{p95:.0f}"


def select_scouts(rows: list[dict], sites: list, plan_id: str) -> list[ScoutVisit]:
    names = {(s["site_id"] if isinstance(s, dict) else s.site_id): (s["name"] if isinstance(s, dict) else s.name) for s in sites}
    by_site: dict[str, list[tuple[float, dict]]] = {}
    for r in rows:
        if float(r["report_age_h"]) < 1 or not _decision_relevant(r):
            continue
        by_site.setdefault(r["site_id"], []).append((voi_score(r), r))
    ranked = []
    for site_id, items in by_site.items():
        items.sort(key=lambda x: (-x[0], SUPPLY_ORDER.index(x[1]["supply_id"])))
        ranked.append((items[0][0], site_id, items))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for n, (score, site_id, items) in enumerate(ranked[: settings.SCOUT_MAX_PER_PLAN], 1):
        top = items[0][1]
        lo, hi = _range_text(float(top["est_qty_p05"]), float(top["est_qty_p95"]))
        supply = top["supply_id"]
        text = (
            f"{supply.capitalize()} at {names.get(site_id, site_id)} is somewhere between {lo} and {hi} "
            f"{settings.unit(supply)}s; a count changes the plan."
        )
        out.append(
            ScoutVisit(
                scout_id=ids.scout_id(plan_id, n),
                site_id=site_id,
                supply_ids=[i[1]["supply_id"] for i in items],
                voi_score=round(score, 2),
                reason_text=text,
            )
        )
    return out
