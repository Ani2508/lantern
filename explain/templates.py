"""Deterministic text: one sentence per gate rule, per-transfer explanations and the plan summary."""

from __future__ import annotations

from lantern_core.config import PLANNER_NAMES, settings
from lantern_core.schemas import RULE_IDS, Plan


def fmt_qty(q: float) -> str:
    q = float(q)
    if abs(q - round(q)) < 0.005:
        return str(int(round(q)))
    return f"{q:.2f}".rstrip("0").rstrip(".")


def unit_plural(supply_id: str, qty: float | None = None) -> str:
    unit = settings.unit(supply_id)
    return unit if qty is not None and abs(float(qty) - 1) < 1e-9 else unit + "s"


def rule_sentence(rule_id: str, level: str, ctx: dict) -> str:
    src, dst, supply = ctx["src_name"], ctx["dst_name"], ctx["supply_id"]
    if rule_id == "R1_SOURCE_RESERVE":
        return f"{src} would fall below its {fmt_qty(ctx['reserve_h'])} h {supply} reserve."
    if rule_id == "R2_DEST_MIN_HOURS":
        return f"{dst} would still have under {fmt_qty(settings.GATE_DEST_MIN_H)} h of {supply} after this transfer."
    if rule_id == "R3_MAX_SIZE":
        return f"This transfer is more than half of {src}'s worst-case {supply} stock."
    if rule_id == "R4_SESSION_DRAW":
        n = ctx.get("n_transfers", 1)
        if level == "BLOCK":
            return f"{n} transfers from {src} together would exceed its session draw limit."
        return f"{n} transfers from {src} together are close to its session draw limit."
    if rule_id == "R5_STALE_SOURCE":
        return f"{src} data is {fmt_qty(ctx['age_h'])} h old."
    raise ValueError(rule_id)


def reason_text(hits: list[tuple[str, str]], ctx: dict) -> str:
    """Join one sentence per rule hit, in rule order; APPROVE gets a fixed sentence."""
    if not hits:
        return "All five safety rules pass."
    ordered = sorted(hits, key=lambda h: RULE_IDS.index(h[0]))
    return " ".join(rule_sentence(r, lvl, ctx) for r, lvl in ordered)


def transfer_sentence(t, names: dict[str, str]) -> str:
    src, dst = names.get(t.source_site_id, t.source_site_id), names.get(t.dest_site_id, t.dest_site_id)
    base = f"Send {fmt_qty(t.qty)} {unit_plural(t.supply_id, t.qty)} of {t.supply_id} from {src} to {dst} ({t.distance_km:.2f} km)."
    if t.decision is None:
        return base + " Not checked by the safety gate."
    return f"{base} {t.decision}: {t.reason_text or ''}".strip()


def template_summary(plan: Plan, names: dict[str, str] | None = None) -> str:
    names = names or {}
    who = PLANNER_NAMES.get(plan.planner, plan.planner)
    c = plan.counts
    n = len(plan.transfers)
    parts = [f"{who} plan at hour {plan.sim_hour}: {n} transfer{'s' if n != 1 else ''}"]
    if plan.apply_gate:
        parts[0] += f" ({c.approve} APPROVE, {c.review} REVIEW, {c.block} BLOCK)."
    else:
        parts[0] += " (safety gate off)."
    blocked = [t for t in plan.transfers if t.decision == "BLOCK"]
    if blocked:
        t = blocked[0]
        parts.append(
            f"The gate blocked {len(blocked)} transfer{'s' if len(blocked) != 1 else ''}, "
            f"e.g. {fmt_qty(t.qty)} {t.supply_id} from {names.get(t.source_site_id, t.source_site_id)}: {t.reason_text}"
        )
    if plan.scouts:
        visits = ", ".join(f"{names.get(s.site_id, s.site_id)} ({', '.join(s.supply_ids)})" for s in plan.scouts)
        parts.append(f"Send scouts to count stock at {visits}.")
    parts.append(f"{fmt_qty(plan.data_loss_pct)}% of sites have no live data.")
    return " ".join(parts)


def apply_templates(plan: Plan, names: dict[str, str] | None = None) -> Plan:
    names = names or {}
    transfers = [t.model_copy(update={"explanation_text": transfer_sentence(t, names)}) for t in plan.transfers]
    p = plan.model_copy(update={"transfers": transfers, "explanation_source": "template"})
    return p.model_copy(update={"summary_text": template_summary(p, names)})
