"""Session-aware deterministic safety gate. Bedrock never touches decisions."""

from __future__ import annotations

from engine.estimator import estimate_row
from explain.templates import reason_text
from gate import rules
from lantern_core import ids, store
from lantern_core.config import settings, utc_now_iso
from lantern_core.schemas import GateLogRow, Transfer


def session_history(session_id: str, exclude_plan_id: str | None = None) -> list[dict]:
    """Earlier gate-log rows of the session. Rows of `exclude_plan_id` are dropped: a re-plan at the
    same hour overwrites that plan, so its old rows must not count as earlier draws."""
    rows = store.query_pk(settings.TABLE_GATE_LOG, session_id)
    return [r for r in rows if r.get("plan_id") != exclude_plan_id]


def session_draws(history: list[dict]) -> dict[tuple[str, str], dict]:
    """Per (source, supply): APPROVE/REVIEW draw so far, transfer count, and p05 at session start."""
    out: dict[tuple[str, str], dict] = {}
    for r in history:
        key = (r["source_site_id"], r["supply_id"])
        d = out.setdefault(key, {"draw": 0.0, "count": 0, "p05_start": float(r["source_p05_before"])})
        if r["decision"] in ("APPROVE", "REVIEW"):
            d["draw"] += float(r["qty"])
            d["count"] += 1
    return out


def _inbound(history: list[dict]) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for r in history:
        if r["decision"] in ("APPROVE", "REVIEW"):
            key = (r["dest_site_id"], r["supply_id"])
            out[key] = out.get(key, 0.0) + float(r["qty"])
    return out


def _names(scenario_id: str, sites: list | None) -> dict[str, str]:
    rows = sites if sites is not None else store.query_pk(settings.TABLE_SITES, scenario_id)
    return {(s["site_id"] if isinstance(s, dict) else s.site_id): (s["name"] if isinstance(s, dict) else s.name) for s in rows}


def evaluate_transfers(
    session_id: str,
    transfers: list[Transfer],
    inventory: list,
    session_aware: bool = True,
    *,
    sites: list | None = None,
    write_log: bool = True,
) -> list[Transfer]:
    """Fill decision, rule_hits and reason_text; write one GateLogRow per transfer.

    session_aware=False drops the earlier-draws part of R1 and all of R4 (single-transfer view).
    """
    if not transfers:
        return []
    inv = {}
    for r in inventory:
        d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        if d.get("est_qty_p05") is None or d.get("burn_rate_per_h") is None:
            d = estimate_row(d)
        inv[d["site_supply"]] = d
    plan_id = transfers[0].plan_id
    pinfo = ids.parse_plan_id(plan_id)
    names = _names(pinfo["scenario_id"], sites)

    history = session_history(session_id, exclude_plan_id=plan_id) if session_aware else []
    draws = session_draws(history)
    inbound = _inbound(history)
    now = utc_now_iso()
    out: list[Transfer] = []
    log_rows: list[dict] = []

    for t in sorted(transfers, key=lambda x: x.priority_rank):
        src = inv.get(ids.site_supply(t.source_site_id, t.supply_id))
        dst = inv.get(ids.site_supply(t.dest_site_id, t.supply_id))
        if src is None or dst is None:
            out.append(
                t.model_copy(update={"decision": "BLOCK", "rule_hits": [], "reason_text": "Unknown source or destination row."})
            )
            continue
        skey, dkey = (t.source_site_id, t.supply_id), (t.dest_site_id, t.supply_id)
        p05 = float(src["est_qty_p05"])
        d = draws.setdefault(skey, {"draw": 0.0, "count": 0, "p05_start": p05})
        reserve_h = settings.reserve_hours(t.supply_id)
        reserve = reserve_h * float(src["burn_rate_per_h"])
        draw_total = d["draw"] + t.qty
        dest_burn = float(dst["burn_rate_per_h"])
        dest_qty_after = float(dst["est_qty_p05"]) + inbound.get(dkey, 0.0) + t.qty
        dest_tts_after = (
            min(float(settings.PLAN_HORIZON_H), dest_qty_after / dest_burn) if dest_burn > 0 else float(settings.PLAN_HORIZON_H)
        )

        hits = [
            rules.r1_source_reserve(p05, draw_total if session_aware else t.qty, reserve),
            rules.r2_dest_min_hours(dest_tts_after),
            rules.r3_max_size(t.qty, p05),
            rules.r4_session_draw(draw_total, d["p05_start"]) if session_aware else None,
            rules.r5_stale_source(float(src["report_age_h"])),
        ]
        hits = [h for h in hits if h]
        decision = rules.combine(hits)
        ctx = {
            "src_name": names.get(t.source_site_id, t.source_site_id),
            "dst_name": names.get(t.dest_site_id, t.dest_site_id),
            "supply_id": t.supply_id,
            "reserve_h": reserve_h,
            "n_transfers": d["count"] + 1,
            "age_h": float(src["report_age_h"]),
        }
        text = reason_text(hits, ctx)
        out.append(t.model_copy(update={"decision": decision, "rule_hits": [h[0] for h in hits], "reason_text": text}))

        if decision != "BLOCK":
            d["draw"] = draw_total
            d["count"] += 1
            inbound[dkey] = inbound.get(dkey, 0.0) + t.qty
        log_rows.append(
            GateLogRow(
                session_id=session_id,
                transfer_id=t.transfer_id,
                plan_id=t.plan_id,
                scenario_id=pinfo["scenario_id"],
                planner=pinfo["planner"],
                source_site_id=t.source_site_id,
                dest_site_id=t.dest_site_id,
                supply_id=t.supply_id,
                qty=t.qty,
                decision=decision,
                rule_hits=[h[0] for h in hits],
                reason_text=text,
                source_p05_before=p05,
                source_p05_after=p05 - draw_total,
                cumulative_draw_qty=draw_total,
                cumulative_draw_limit=settings.GATE_SESSION_DRAW_FRAC * d["p05_start"],
                source_report_age_h=float(src["report_age_h"]),
                dest_tts_p05_h_after=dest_tts_after,
                created_at=now,
            ).to_item()
        )
    if write_log and session_aware:
        store.batch_put(settings.TABLE_GATE_LOG, log_rows)
    return out
