"""Writes the latest Lantern plan for the static fallback page. OWNER: M4.  DRAFT by M3 for M4 review.

The page (web/fallback/index.html) reads fallback/plan.json from the web
bucket, so it keeps working when the API is switched off.
"""

from __future__ import annotations

from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import Plan


def write_fallback(plan: Plan) -> None:
    if not settings.notify_enabled:
        return
    names = {s["site_id"]: s["name"] for s in store.query_pk(settings.table_sites, plan.scenario_id)}
    body = {**plan.to_item(), "site_names": names}
    if settings.lantern_mode == "aws":
        import json

        import boto3

        boto3.client("s3", region_name=settings.aws_region).put_object(
            Bucket=settings.web_bucket, Key="fallback/plan.json", Body=json.dumps(body),
            ContentType="application/json", CacheControl="max-age=30",
        )
        return
    store.put_json("fallback/plan.json", body)
