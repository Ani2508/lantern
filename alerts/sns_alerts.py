"""One short SNS alert per Lantern plan (email, plus SMS where the sandbox allows)."""

from __future__ import annotations

import logging

from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import Plan

log = logging.getLogger(__name__)
MAX_LEN = 160


def build_message(plan: Plan) -> str:
    c = plan.counts
    msg = f"LANTERN h{plan.sim_hour:03d}: {c.approve} approved, {c.review} review, {c.block} blocked."
    if plan.scouts:
        s = plan.scouts[0]
        msg += f" Scout {s.site_id} {s.supply_ids[0]}."
    if settings.FALLBACK_PUBLIC_URL:
        msg += f" {settings.FALLBACK_PUBLIC_URL}"
    return msg[:MAX_LEN]


def publish_plan(plan: Plan) -> None:
    msg = build_message(plan)
    if not settings.NOTIFY_ENABLED or settings.LANTERN_MODE != "aws":
        log.info("alert (not sent: notify=%s mode=%s): %s", settings.NOTIFY_ENABLED, settings.LANTERN_MODE, msg)
        return
    store.aws_client("sns").publish(TopicArn=settings.SNS_TOPIC_ARN, Message=msg, Subject=f"Lantern plan h{plan.sim_hour:03d}")
    log.info("alert sent: %s", msg)
