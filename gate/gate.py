"""Session-aware safety gate (contract 2.8). OWNER: M4.  DRAFT by M3 for M4 review.

evaluate_transfers(session_id, transfers, inventory, session_aware=True):
  1. load earlier rows of this session from lantern-dev-gate-log
  2. process transfers in priority_rank order, adding each APPROVE/REVIEW to
     the running draw per (source, supply); BLOCKed transfers never count
  3. combine rule hits: BLOCK > REVIEW > APPROVE
  4. fill decision, rule_hits, reason_text; write one gate-log row each

session_aware=False drops the earlier-draws part of R1 and all of R4 and
writes no log rows; it exists only for the session-vs-single metric.
Inventory rows must carry estimates (run_plan passes estimated rows; if not,
they are estimated here).
"""

from __future__ import annotations

from engine.estimator import estimate_row, tts_hours
from explain.templates import reason_text
from gate import rules
from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import iso
from lantern_core.schemas import SUPPLIES, Decision, GateLogRow, InventoryState, Transfer

IS_STUB = False


def _planner_of(plan_id: str) -> str:
    for p in ("equal_split", "naive", "lantern"):
        if f"_{p}_h" in plan_id:
            return p
    return "lantern"


def _site_names(scenario_id: str) -> dict[str, str]:
    return {s["site_id"]: s["name"] for s in store.query_pk(settings.table_sites, scenario_id)}


def evaluate_transfers(
    session_id: str,
    transfers: list[Transfer],
    inventory: list[InventoryState],
    session_aware: bool = True,
) -> list[Transfer]:
    if not transfers:
        return []
    est = {}
    for r in inventory:
        if r.est_qty_p05 is None:
            r = estimate_row(r)
        est[(r.site_id, r.supply_id)] = r
    scenario_id = inventory[0].scenario_id if inventory else ""
    names = _site_names(scenario_id) if scenario_id else {}

    # session history: draws so far and each source's p05 at session start
    drawn: dict[tuple[str, str], float] = {}
    start_p05: dict[tuple[str, str], float] = {}
    count: dict[tuple[str, str], int] = {}
    plan_ids = {t.plan_id for t in transfers}
    if session_aware:
        for row in store.query_pk(settings.table_gate_log, session_id):
            if row.get("plan_id") in plan_ids:
                continue  # re-gating the same plan: start clean for it
            key = (row["source_site_id"], row["supply_id"])
            start_p05.setdefault(key, float(row.get("source_p05_before", 0.0)))
            if row["decision"] != Decision.BLOCK.value:
                drawn[key] = drawn.get(key, 0.0) + float(row["qty"])
                count[key] = count.get(key, 0) + 1

    now = iso()
    out: list[Transfer] = []
    log_rows: list[dict] = []
    for t in sorted(transfers, key=lambda t: t.priority_rank):
        key = (t.source_site_id, t.supply_id)
        src = est.get(key)
        dst = est.get((t.dest_site_id, t.supply_id))
        if src is None:
            decision, ids, text = "BLOCK", [rules.R1], "No inventory record for the source."
            out.append(t.model_copy(update={"decision": decision, "rule_hits": ids, "reason_text": text}))
            continue
        p05 = src.est_qty_p05 or 0.0
        burn = src.burn_rate_per_h or 0.0
        crit = SUPPLIES[t.supply_id].critical
        res_h = rules.reserve_hours(crit)
        reserve = res_h * burn
        before = drawn.get(key, 0.0) if session_aware else 0.0
        cum = before + t.qty
        limit = settings.gate_session_draw_frac * start_p05.get(key, p05)
        dest_after = tts_hours((dst.est_qty_p05 or 0.0) + t.qty, dst.burn_rate_per_h or 0.0) if dst else 0.0
        n = count.get(key, 0) + 1

        hits = [
            rules.r1_source_reserve(p05, cum, reserve),
            rules.r2_dest_min_hours(dest_after) if dst else None,
            rules.r3_max_size(t.qty, p05),
            rules.r4_session_draw(cum, limit) if session_aware else None,
            rules.r5_stale_source(src.report_age_h),
        ]
        decision, ids = rules.combine(hits)
        text = reason_text(
            ids, decision, source=names.get(t.source_site_id, t.source_site_id),
            supply=t.supply_id, unit=SUPPLIES[t.supply_id].unit, n=n, cum=cum, limit=limit,
            reserve_h=res_h, age_h=src.report_age_h, dest_after_h=dest_after,
        )
        out.append(t.model_copy(update={"decision": decision, "rule_hits": ids, "reason_text": text}))

        if session_aware:
            log_rows.append(GateLogRow(
                session_id=session_id, transfer_id=t.transfer_id, plan_id=t.plan_id, scenario_id=scenario_id,
                planner=_planner_of(t.plan_id),
                source_site_id=t.source_site_id, dest_site_id=t.dest_site_id, supply_id=t.supply_id,
                qty=t.qty, decision=decision, rule_hits=ids, reason_text=text,
                source_p05_before=start_p05.get(key, p05), source_p05_after=p05 - cum,
                cumulative_draw_qty=cum if decision != "BLOCK" else before,
                cumulative_draw_limit=limit, source_report_age_h=src.report_age_h,
                dest_tts_p05_after_h=dest_after, created_at=now,
            ).to_item())
            start_p05.setdefault(key, p05)
            if decision != "BLOCK":
                drawn[key] = cum
                count[key] = n
    if log_rows:
        store.batch_put(settings.table_gate_log, log_rows)
    return out
