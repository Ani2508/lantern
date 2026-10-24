"""Plain-English plan explanations from Bedrock, validated, with a deterministic template fallback.

Bedrock only explains decisions already made; it never adds, removes or changes a transfer or decision.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from explain import bedrock_client
from explain.templates import apply_templates, fmt_qty
from lantern_core import store
from lantern_core.config import PLANNER_NAMES, settings
from lantern_core.schemas import Plan

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You explain emergency supply transfer plans to a shelter coordinator during a disaster. "
    "Every decision in the plan has ALREADY been made by deterministic safety rules. Explain those decisions "
    "in plain English, briefly and calmly. Never change, add or remove a transfer, a quantity or a decision, "
    "and never suggest a different decision. Use each transfer's decision word exactly as given "
    "(APPROVE, REVIEW or BLOCK) and do not use the other decision words for that transfer. "
    "The data is synthetic. Reply with JSON only, in the form "
    '{"summary_text": "<2-4 sentences covering the transfers and any scout visits>", '
    '"explanations": {"<transfer_id>": "<1-2 sentences>"}} '
    "with one entry for every transfer_id."
)

_DECISION_WORDS = {
    "APPROVE": re.compile(r"\bapprov(e|ed|es|al|ing)\b", re.I),
    "REVIEW": re.compile(r"\breview(s|ed|ing)?\b", re.I),
    "BLOCK": re.compile(r"\bblock(s|ed|ing)?\b", re.I),
}

_cache: dict[str, tuple[str, dict[str, str], str]] = {}


def clear_cache() -> None:
    _cache.clear()


def _names(plan: Plan, sites: list | None) -> dict[str, str]:
    rows = sites if sites is not None else store.query_pk(settings.TABLE_SITES, plan.scenario_id)
    return {(s["site_id"] if isinstance(s, dict) else s.site_id): (s["name"] if isinstance(s, dict) else s.name) for s in rows}


def _facts(plan: Plan, names: dict[str, str]) -> dict:
    return {
        "planner": PLANNER_NAMES.get(plan.planner, plan.planner),
        "sim_hour": plan.sim_hour,
        "percent_sites_without_live_data": plan.data_loss_pct,
        "safety_gate_applied": plan.apply_gate,
        "counts": plan.counts.model_dump(),
        "transfers": [
            {
                "transfer_id": t.transfer_id,
                "from": names.get(t.source_site_id, t.source_site_id),
                "to": names.get(t.dest_site_id, t.dest_site_id),
                "supply": t.supply_id,
                "qty": fmt_qty(t.qty),
                "unit": settings.unit(t.supply_id) + "s",
                "distance_km": t.distance_km,
                "decision": t.decision or "NOT_CHECKED",
                "rule_hits": t.rule_hits,
                "gate_reason": t.reason_text,
            }
            for t in plan.transfers
        ],
        "scout_visits": [
            {"site": names.get(s.site_id, s.site_id), "supplies": s.supply_ids, "why": s.reason_text} for s in plan.scouts
        ],
    }


def _cache_key(plan: Plan) -> str:
    sig = json.dumps(
        [
            plan.plan_id,
            [(t.transfer_id, t.source_site_id, t.dest_site_id, t.qty, t.decision, t.rule_hits) for t in plan.transfers],
            [(s.site_id, s.supply_ids) for s in plan.scouts],
        ],
        sort_keys=True,
    )
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()


def validate_reply(plan: Plan, obj: dict) -> tuple[str, dict[str, str]]:
    summary = obj.get("summary_text")
    expl = obj.get("explanations")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 1500:
        raise ValueError("summary_text missing or too long")
    if not isinstance(expl, dict):
        raise ValueError("explanations missing")
    out = {}
    for t in plan.transfers:
        text = expl.get(t.transfer_id)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"no explanation for {t.transfer_id}")
        for word, rx in _DECISION_WORDS.items():
            if t.decision and word != t.decision and rx.search(text):
                raise ValueError(f"explanation for {t.transfer_id} contradicts its decision {t.decision}")
        out[t.transfer_id] = text.strip()
    extra = set(expl) - {t.transfer_id for t in plan.transfers}
    if extra:
        raise ValueError(f"explanations for unknown transfers: {sorted(extra)}")
    return summary.strip(), out


def explain_plan(plan: Plan, sites: list | None = None) -> Plan:
    """Return the plan with summary_text, explanation_text and explanation_source filled in."""
    names = _names(plan, sites)
    templated = apply_templates(plan, names)
    if not settings.BEDROCK_ENABLED:
        return templated
    key = _cache_key(plan)
    hit = _cache.get(key)
    if hit is None:
        facts = json.dumps(_facts(plan, names), indent=1)
        for model_id in bedrock_client.model_ids():
            try:
                reply = bedrock_client.converse_text(model_id, SYSTEM_PROMPT, "Plan facts (JSON):\n" + facts)
                summary, expl = validate_reply(plan, bedrock_client.extract_json(reply))
                hit = (summary, expl, model_id)
                _cache[key] = hit
                break
            except Exception as e:
                log.warning("bedrock explain failed with %s: %s", model_id, e)
    if hit is None:
        log.info("explanation_source=template plan_id=%s", plan.plan_id)
        return templated
    summary, expl, model_id = hit
    transfers = [t.model_copy(update={"explanation_text": expl[t.transfer_id]}) for t in templated.transfers]
    log.info("explanation_source=bedrock plan_id=%s model=%s", plan.plan_id, model_id)
    return templated.model_copy(update={"transfers": transfers, "summary_text": summary, "explanation_source": "bedrock"})
