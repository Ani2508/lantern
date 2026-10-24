"""Static fallback page data: fallback/plan.json in the web bucket (and web/fallback/ locally).

CLI (python -m alerts.fallback_publish): rewrite plan.json from the latest demo Lantern plan in the
store, or from a fresh in-memory hour-9 run if there is none.
"""

from __future__ import annotations

import json
import logging

from lantern_core import store
from lantern_core.config import BANNER, DEMO_SCENARIO_ID, PLANNER_NAMES, ROOT_DIR, settings, utc_now_iso
from lantern_core.schemas import Plan

log = logging.getLogger(__name__)
FALLBACK_KEY = "fallback/plan.json"
LOCAL_WEB_FILE = ROOT_DIR / "web" / "fallback" / "plan.json"


def build_payload(plan: Plan, sites: list | None = None) -> dict:
    rows = sites if sites is not None else store.query_pk(settings.TABLE_SITES, plan.scenario_id)
    names = {s["site_id"]: s["name"] for s in (r if isinstance(r, dict) else r.model_dump() for r in rows)}
    return {
        "banner": BANNER,
        "updated_at": utc_now_iso(),
        "sim_time": settings.sim_hour_to_iso(plan.sim_hour),
        "planner_name": PLANNER_NAMES.get(plan.planner, plan.planner),
        "site_names": names,
        "plan": plan.to_item(),
    }


def write_fallback(plan: Plan, sites: list | None = None) -> None:
    body = json.dumps(build_payload(plan, sites), ensure_ascii=False, indent=1)
    store.put_object(FALLBACK_KEY, body, bucket=settings.WEB_BUCKET, content_type="application/json")
    if settings.LANTERN_MODE == "local":
        LOCAL_WEB_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_WEB_FILE.write_text(body, encoding="utf-8")
    log.info("fallback plan.json written for %s", plan.plan_id)


def latest_plan(scenario_id: str, planner: str = "lantern") -> Plan | None:
    plans = [p for p in store.query_pk(settings.TABLE_PLANS, scenario_id) if p.get("planner") == planner]
    if not plans:
        return None
    plans.sort(key=lambda p: (p["sim_hour"], p.get("created_at", "")))
    return Plan.model_validate(plans[-1])


def main() -> None:
    plan = latest_plan(DEMO_SCENARIO_ID)
    sites = None
    if plan is None:
        from api import demo_story

        plan, sites = demo_story.hour9_lantern_in_memory()
    write_fallback(plan, sites)
    where = LOCAL_WEB_FILE if settings.LANTERN_MODE == "local" else f"{settings.WEB_BUCKET}/{FALLBACK_KEY}"
    print(f"fallback plan.json written ({plan.plan_id}) -> {where}")


if __name__ == "__main__":
    main()
