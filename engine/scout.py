"""Scout picker: where a fresh count would change the plan. OWNER: M3.

Only sites with stale data are candidates. Score per (site, supply):
    range term   min(1, (p95 - p05) / max(p50, 1))
    + 0.5        if the optimizer skipped this stale site as a source while a
                 need for that supply went unmet (a count could unlock stock)
    + 0.3        if the site itself may need a delivery (p05 below its own need)
    x 1.0 for critical supplies, 0.6 otherwise, capped at 1.
A site's score is its best supply; keep scores >= 0.2, top SCOUT_MAX_PER_PLAN.
"""

from __future__ import annotations

from engine.optimizer import DEST_SUPPLIES, ProposeResult
from lantern_core.config import settings
from lantern_core.ids import scout_id
from lantern_core.schemas import SUPPLIES, InventoryState, ScoutVisit

MIN_SCORE = 0.2


def _fmt(q: float) -> str:
    return f"{q:,.0f}"


def pick_scouts(
    inventory: list[InventoryState], sites: dict[str, dict], result: ProposeResult, plan_id: str
) -> list[ScoutVisit]:
    unmet_supplies = {sup for (_, sup) in result.unmet}
    per_site: dict[str, list[tuple[float, InventoryState, str]]] = {}
    for r in inventory:
        if r.data_status != "stale":
            continue
        stype = sites.get(r.site_id, {}).get("site_type", "shelter")
        is_skipped_source = (r.site_id, r.supply_id) in result.skipped_stale_sources
        if r.supply_id not in DEST_SUPPLIES.get(stype, set()) and not is_skipped_source:
            continue  # e.g. food at a pharmacy: a count would not change the plan
        p05, p50, p95 = r.est_qty_p05 or 0.0, r.est_qty_p50 or 0.0, r.est_qty_p95 or 0.0
        score = min(1.0, (p95 - p05) / max(p50, 1.0))
        why = "shows whether it needs a delivery"
        if is_skipped_source and r.supply_id in unmet_supplies:
            score += 0.5
            why = "could free stock for sites that are short"
        if p05 < (r.burn_rate_per_h or 0.0) * settings.plan_horizon_h:
            score += 0.3
        score *= 1.0 if SUPPLIES[r.supply_id].critical else 0.6
        score = min(1.0, score)
        if score >= MIN_SCORE:
            per_site.setdefault(r.site_id, []).append((score, r, why))

    ranked = sorted(per_site.items(), key=lambda kv: -max(s for s, _, _ in kv[1]))
    scouts: list[ScoutVisit] = []
    for site_id, items in ranked[: settings.scout_max_per_plan]:
        items.sort(key=lambda x: -x[0])
        best, row, why = items[0]
        unit = SUPPLIES[row.supply_id].unit
        name = sites.get(site_id, {}).get("name", site_id)
        reason = (
            f"{row.supply_id.capitalize()} at {name}: last count {_fmt(row.last_reported_qty)} {unit}s, "
            f"{row.report_age_h:.0f} h old; now somewhere between {_fmt(row.est_qty_p05 or 0)} and "
            f"{_fmt(row.est_qty_p95 or 0)}. A fresh count {why}."
        )
        scouts.append(ScoutVisit(
            scout_id=scout_id(plan_id, len(scouts) + 1),
            site_id=site_id,
            supply_ids=[r.supply_id for _, r, _ in items],
            voi_score=round(best, 2),
            reason_text=reason,
        ))
    return scouts
