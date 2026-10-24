"""SMS alert for each Lantern plan via SNS. OWNER: M4.  DRAFT by M3 for M4 review.

Respects NOTIFY_ENABLED (also checked by run_plan). Local/memory mode prints.
"""

from __future__ import annotations

import logging

from lantern_core.config import settings
from lantern_core.schemas import Plan

log = logging.getLogger("lantern.alerts")


def format_sms(plan: Plan) -> str:
    c = plan.counts
    msg = f"LANTERN h{plan.sim_hour:03d}: {c.approve} approved, {c.review} review, {c.block} blocked."
    if plan.scouts:
        msg += " Scout " + ", ".join(s.site_id for s in plan.scouts) + "."
    if settings.fallback_url:
        msg += " " + settings.fallback_url
    return msg[:160]


def publish_plan(plan: Plan) -> None:
    if not settings.notify_enabled:
        return
    msg = format_sms(plan)
    if settings.lantern_mode != "aws":
        print(f"[sms] {msg}")
        return
    import boto3

    boto3.client("sns", region_name=settings.aws_region).publish(
        TopicArn=settings.sns_topic_arn, Message=msg, Subject="Lantern plan"
    )
    log.info("sms published for %s", plan.plan_id)
