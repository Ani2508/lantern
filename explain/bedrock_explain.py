"""Plain-English explanations via Amazon Bedrock. OWNER: M4.  DRAFT by M3 for M4 review.

Bedrock only explains decisions already made by the optimizer and the gate.
It can never add, drop or change a transfer or a decision: the reply is
validated and, on any problem (off, timeout, bad JSON, missing ids, a decision
word that contradicts the gate), deterministic templates are used instead.
Cached by plan_id so re-running the demo is instant and free.
"""

from __future__ import annotations

import json
import logging

from explain.templates import plan_summary, transfer_explanation
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import Plan

log = logging.getLogger("lantern.explain")
_CACHE: dict[str, dict] = {}

SYSTEM = (
    "You explain a disaster supply plan to a shelter coordinator in plain English. "
    "The decisions are final and were made by a planner and a safety gate. Never change, add or "
    "remove a transfer, never change a decision (APPROVE, REVIEW, BLOCK), and never invent numbers. "
    "Say clearly when data is old and the numbers are estimates. Keep each explanation to one or two "
    "short sentences. Reply with JSON only: "
    '{"summary_text": "...", "explanations": {"<transfer_id>": "..."}}'
)


def _names(scenario_id: str) -> dict[str, str]:
    try:
        return {s["site_id"]: s["name"] for s in store.query_pk(settings.table_sites, scenario_id)}
    except Exception:  # noqa: BLE001
        return {}


def _template(plan: Plan) -> Plan:
    names = _names(plan.scenario_id)
    transfers = [t.model_copy(update={"explanation_text": transfer_explanation(t, names)}) for t in plan.transfers]
    plan = plan.model_copy(update={"transfers": transfers})
    return plan.model_copy(update={"summary_text": plan_summary(plan), "explanation_source": "template"})


def _ask_bedrock(plan: Plan) -> dict:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "bedrock-runtime", region_name=settings.aws_region,
        config=Config(read_timeout=settings.bedrock_timeout_s, connect_timeout=3, retries={"max_attempts": 1}),
    )
    payload = {
        "hour": plan.sim_hour, "planner": plan.planner, "data_loss_pct": plan.data_loss_pct,
        "transfers": [t.model_dump(include={"transfer_id", "source_site_id", "dest_site_id", "supply_id", "qty",
                                            "decision", "rule_hits", "reason_text"}) for t in plan.transfers],
        "scouts": [s.model_dump(include={"site_id", "supply_ids", "reason_text"}) for s in plan.scouts],
        "site_names": _names(plan.scenario_id),
    }
    resp = client.converse(
        modelId=settings.bedrock_model_id,
        system=[{"text": SYSTEM}],
        messages=[{"role": "user", "content": [{"text": json.dumps(payload)}]}],
        inferenceConfig={"temperature": 0.2, "maxTokens": 600},
    )
    text = resp["output"]["message"]["content"][0]["text"]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


def _valid(reply: dict, plan: Plan) -> bool:
    exps = reply.get("explanations")
    if not isinstance(reply.get("summary_text"), str) or not isinstance(exps, dict):
        return False
    for t in plan.transfers:
        text = exps.get(t.transfer_id)
        if not isinstance(text, str) or not text.strip():
            return False
        upper = text.upper()
        for word in ("APPROVE", "REVIEW", "BLOCK"):
            if word in upper and word != (t.decision or ""):
                return False  # contradicts the gate
    return True


def explain_plan(plan: Plan) -> Plan:
    base = _template(plan)
    if not settings.bedrock_enabled or not settings.bedrock_model_id or settings.lantern_mode == "memory":
        return base
    reply = _CACHE.get(plan.plan_id)
    if reply is None:
        try:
            reply = _ask_bedrock(plan)
        except Exception:  # noqa: BLE001
            log.warning("Bedrock unavailable; using templates", exc_info=True)
            return base
        if not _valid(reply, plan):
            log.warning("Bedrock reply failed validation; using templates")
            return base
        _CACHE[plan.plan_id] = reply
    transfers = [t.model_copy(update={"explanation_text": reply["explanations"][t.transfer_id]}) for t in base.transfers]
    return base.model_copy(update={"transfers": transfers, "summary_text": reply["summary_text"],
                                   "explanation_source": "bedrock"})
