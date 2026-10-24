"""The five gate rules. Pure functions; each returns (rule_id, "BLOCK"|"REVIEW") or None."""

from __future__ import annotations

from lantern_core.config import Settings
from lantern_core.config import settings as default_settings

Hit = tuple[str, str] | None


def r1_source_reserve(source_p05: float, draw_total: float, reserve: float) -> Hit:
    """BLOCK when the source's worst-case stock minus all session draws falls below its reserve."""
    if source_p05 - draw_total < reserve:
        return ("R1_SOURCE_RESERVE", "BLOCK")
    return None


def r2_dest_min_hours(dest_tts_p05_after: float, s: Settings = default_settings) -> Hit:
    """REVIEW when the destination still has under GATE_DEST_MIN_H hours after the transfer(s)."""
    if dest_tts_p05_after < s.GATE_DEST_MIN_H:
        return ("R2_DEST_MIN_HOURS", "REVIEW")
    return None


def r3_max_size(qty: float, source_p05: float, s: Settings = default_settings) -> Hit:
    """BLOCK a single transfer larger than GATE_MAX_TRANSFER_FRAC of the source's worst case."""
    if qty > s.GATE_MAX_TRANSFER_FRAC * source_p05:
        return ("R3_MAX_SIZE", "BLOCK")
    return None


def r4_session_draw(draw_total: float, source_p05_session_start: float, s: Settings = default_settings) -> Hit:
    """BLOCK above the session draw limit; REVIEW above GATE_SESSION_REVIEW_FRAC of it (both strict)."""
    limit = s.GATE_SESSION_DRAW_FRAC * source_p05_session_start
    if draw_total > limit:
        return ("R4_SESSION_DRAW", "BLOCK")
    if draw_total > s.GATE_SESSION_REVIEW_FRAC * limit:
        return ("R4_SESSION_DRAW", "REVIEW")
    return None


def r5_stale_source(source_report_age_h: float, s: Settings = default_settings) -> Hit:
    """REVIEW when the source's data is older than GATE_STALE_REVIEW_H."""
    if source_report_age_h > s.GATE_STALE_REVIEW_H:
        return ("R5_STALE_SOURCE", "REVIEW")
    return None


def combine(hits: list[Hit]) -> str:
    """BLOCK beats REVIEW beats APPROVE."""
    levels = {h[1] for h in hits if h}
    if "BLOCK" in levels:
        return "BLOCK"
    if "REVIEW" in levels:
        return "REVIEW"
    return "APPROVE"
