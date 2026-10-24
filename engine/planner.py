"""run_plan: load -> estimate -> forecast -> propose -> gate -> scouts -> explain -> save -> notify."""

from __future__ import annotations

import logging
import time

from baselines import equal_split
from engine import forecaster, optimizer, scout
from engine.estimator import estimate
from explain.templates import apply_templates
from gate import gate
from lantern_core import ids, store
from lantern_core.config import settings, utc_now_iso
from lantern_core.schemas import Counts, InventoryState, Plan, Transfer

log = logging.getLogger(__name__)


def _context(scenario_id: str, sim_hour: int, sites: list[dict]) -> dict:
    """Forecaster context from raw inputs only (hazard from the id, weather from raw/)."""
    try:
        hazard = ids.parse_scenario_id(scenario_id)["hazard"]
    except ValueError:
        hazard = None
    weather = {w["sim_hour"]: w for w in store.get_jsonl(f"raw/scenarios/{scenario_id}/weather.jsonl")}
    w = weather.get(sim_hour, {})
    return {
        "hazard": hazard,
        "temp_c": w.get("temp_c", 0.0),
        "hazard_level": w.get("hazard_level", 0),
        "site_types": {s["site_id"]: s["site_type"] for s in sites},
    }


def data_loss_pct(rows: list[dict]) -> float:
    """Percent of sites with no live row."""
    sites: dict[str, bool] = {}
    for r in rows:
        sites[r["site_id"]] = sites.get(r["site_id"], False) or r["data_status"] == "live"
    if not sites:
        return 0.0
    return round(100.0 * sum(1 for live in sites.values() if not live) / len(sites), 2)


def count(transfers: list[Transfer]) -> Counts:
    return Counts(
        approve=sum(t.decision == "APPROVE" for t in transfers),
        review=sum(t.decision == "REVIEW" for t in transfers),
        block=sum(t.decision == "BLOCK" for t in transfers),
    )


def run_plan(
    scenario_id: str,
    sim_hour: int,
    planner: str,
    session_id: str,
    apply_gate: bool = True,
) -> Plan:
    t0 = time.perf_counter()
    pid = ids.plan_id(scenario_id, planner, sim_hour)
    sites = store.query_pk(settings.TABLE_SITES, scenario_id)
    inventory = store.query_pk(settings.TABLE_INVENTORY, scenario_id)
    if not inventory:
        raise LookupError(f"no inventory for scenario {scenario_id}; reset it first")

    rows = estimate(inventory)
    try:
        ctx = _context(scenario_id, sim_hour, sites)
        feats = [{**r, "sim_hour": sim_hour, "site_type": ctx["site_types"].get(r["site_id"]), **{k: ctx[k] for k in ("hazard", "temp_c", "hazard_level")}} for r in rows]
        for r, (a, b, c) in zip(rows, forecaster.predict(feats), strict=True):
            r["tts_p05_h"], r["tts_p50_h"], r["tts_p95_h"] = a, b, c
    except Exception:
        log.exception("forecaster failed; keeping heuristic tts")

    history = gate.session_history(session_id, exclude_plan_id=pid)
    if planner == "equal_split":
        transfers = equal_split.propose(rows, sim_hour, pid, sites=sites)
    else:
        transfers = optimizer.propose(rows, sites, planner, pid, gate.session_draws(history))

    if apply_gate and transfers:
        try:
            transfers = gate.evaluate_transfers(session_id, transfers, rows, sites=sites)
        except Exception:
            log.exception("gate failed; holding every transfer for review")
            transfers = [
                t.model_copy(update={"decision": "REVIEW", "rule_hits": [], "reason_text": "Safety gate unavailable; review by hand."})
                for t in transfers
            ]

    scouts = scout.select_scouts(rows, sites, pid) if planner == "lantern" else []

    plan = Plan(
        scenario_id=scenario_id,
        plan_id=pid,
        session_id=session_id,
        planner=planner,
        sim_hour=sim_hour,
        data_loss_pct=data_loss_pct(rows),
        apply_gate=apply_gate,
        transfers=transfers,
        scouts=scouts,
        counts=count(transfers),
        created_at=utc_now_iso(),
    )
    try:
        from explain.bedrock_explain import explain_plan

        plan = explain_plan(plan, sites=sites)
    except Exception:
        log.exception("explain failed; using templates")
        plan = apply_templates(plan, {s["site_id"]: s["name"] for s in sites})

    plan = plan.model_copy(update={"runtime_ms": round((time.perf_counter() - t0) * 1000, 2)})
    store.put_item(settings.TABLE_PLANS, plan.to_item())
    store.batch_put(settings.TABLE_INVENTORY, [InventoryState.model_validate(r).to_item() for r in rows])

    if planner == "lantern" and settings.NOTIFY_ENABLED:
        try:
            from alerts.fallback_publish import write_fallback
            from alerts.sns_alerts import publish_plan

            publish_plan(plan)
            write_fallback(plan, sites=sites)
        except Exception:
            log.exception("alert or fallback publish failed; the plan is saved")
    return plan
