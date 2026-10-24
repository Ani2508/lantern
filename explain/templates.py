"""Deterministic reason, explanation and summary text. OWNER: M4.  DRAFT by M3 for M4 review.

These sentences are the fallback whenever Bedrock is off, slow or wrong, so the
demo never depends on the model.
"""

from __future__ import annotations

from lantern_core.schemas import SUPPLIES, Plan, Transfer


def _q(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 10 else f"{x:,.1f}".rstrip("0").rstrip(".")


def reason_text(
    rule_ids: list[str], decision: str, *, source: str, supply: str, unit: str, n: int, cum: float,
    limit: float, reserve_h: float, age_h: float, dest_after_h: float,
) -> str:
    if not rule_ids:
        return "All safety checks passed."
    parts = []
    if "R1_SOURCE_RESERVE" in rule_ids:
        parts.append(f"{n} transfers from {source} together would leave {supply} below its {reserve_h:.0f} h reserve.")
    if "R4_SESSION_DRAW" in rule_ids:
        if decision == "BLOCK" and "R1_SOURCE_RESERVE" not in rule_ids:
            parts.append(f"{n} transfers from {source} would draw {_q(cum)} {unit}s, over this session's limit of {_q(limit)}.")
        elif decision != "BLOCK":
            parts.append(f"{n} transfers from {source} draw {_q(cum)} {unit}s, close to this session's limit of {_q(limit)}.")
    if "R3_MAX_SIZE" in rule_ids:
        parts.append(f"This load is more than half of what {source} may have left.")
    if "R2_DEST_MIN_HOURS" in rule_ids:
        parts.append(f"The destination would still run out in about {dest_after_h:.0f} h.")
    if "R5_STALE_SOURCE" in rule_ids:
        parts.append(f"{source} data is {age_h:.0f} h old.")
    return " ".join(parts)


def transfer_explanation(t: Transfer, names: dict[str, str]) -> str:
    unit = SUPPLIES[t.supply_id].unit
    src, dst = names.get(t.source_site_id, t.source_site_id), names.get(t.dest_site_id, t.dest_site_id)
    head = f"Move {_q(t.qty)} {unit}s of {t.supply_id} from {src} to {dst} ({t.distance_km:.1f} km)."
    if t.decision == "BLOCK":
        return f"{head} Blocked: {t.reason_text}"
    if t.decision == "REVIEW":
        return f"{head} Needs a person to check: {t.reason_text}"
    if t.decision == "APPROVE":
        return f"{head} Approved; it keeps a safe reserve at {src}."
    return head


def plan_summary(plan: Plan) -> str:
    c = plan.counts
    parts = [f"Hour {plan.sim_hour}: {len(plan.transfers)} transfers "
             f"({c.approve} approved, {c.review} for review, {c.block} blocked)."]
    if plan.data_loss_pct:
        parts.append(f"{plan.data_loss_pct:.0f}% of sites have no live data.")
    if plan.scouts:
        parts.append("Send a scout to " + ", ".join(s.site_id for s in plan.scouts) + " for a fresh count.")
    return " ".join(parts)
