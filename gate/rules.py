"""Gate rules R1-R5 (contract 2.8). OWNER: M4.  DRAFT by M3 for M4 review.

Each rule is a pure function returning (rule_id, "BLOCK" | "REVIEW") or None.
All thresholds come from settings (GATE_*).
"""

from __future__ import annotations

from lantern_core.config import settings

Hit = tuple[str, str] | None

R1 = "R1_SOURCE_RESERVE"
R2 = "R2_DEST_MIN_HOURS"
R3 = "R3_MAX_SIZE"
R4 = "R4_SESSION_DRAW"
R5 = "R5_STALE_SOURCE"
ORDER = [R1, R2, R3, R4, R5]


def reserve_hours(critical: bool) -> float:
    return settings.gate_source_reserve_h_critical if critical else settings.gate_source_reserve_h


def r1_source_reserve(source_p05: float, drawn_incl_this: float, reserve_qty: float) -> Hit:
    """Source worst case minus this and earlier session draws must stay >= reserve."""
    return (R1, "BLOCK") if source_p05 - drawn_incl_this < reserve_qty - 1e-9 else None


def r2_dest_min_hours(dest_tts_p05_after_h: float) -> Hit:
    return (R2, "REVIEW") if dest_tts_p05_after_h < settings.gate_dest_min_h else None


def r3_max_size(qty: float, source_p05: float) -> Hit:
    return (R3, "BLOCK") if qty > settings.gate_max_transfer_frac * source_p05 + 1e-9 else None


def r4_session_draw(drawn_incl_this: float, limit: float) -> Hit:
    if drawn_incl_this > limit + 1e-9:
        return (R4, "BLOCK")
    if drawn_incl_this > settings.gate_session_review_frac * limit + 1e-9:
        return (R4, "REVIEW")
    return None


def r5_stale_source(source_report_age_h: float) -> Hit:
    return (R5, "REVIEW") if source_report_age_h > settings.gate_stale_review_h else None


def combine(hits: list[Hit]) -> tuple[str, list[str]]:
    """BLOCK if any BLOCK, else REVIEW if any REVIEW, else APPROVE. Rule ids in R1..R5 order."""
    real = [h for h in hits if h]
    ids = sorted({h[0] for h in real}, key=ORDER.index)
    if any(h[1] == "BLOCK" for h in real):
        return "BLOCK", ids
    if real:
        return "REVIEW", ids
    return "APPROVE", ids
