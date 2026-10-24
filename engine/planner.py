"""run_plan: the orchestrator (contract 2.7). OWNER: M3.

Order: load inventory -> estimate -> forecast -> propose (optimizer, or
equal_split) -> gate (if apply_gate) -> scouts (lantern only) -> explain ->
save plan + inventory -> alert + fallback (lantern only, if NOTIFY_ENABLED).

Gate, explain and alerts belong to M4. A failure in explain or alerts never
loses the plan; a gate failure does stop it (we never ship ungated transfers).
"""

from __future__ import annotations

import logging
import time

from engine import estimator, forecaster, optimizer, scout
from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import iso
from lantern_core.ids import plan_id as make_plan_id
from lantern_core.schemas import InventoryState, Plan, Planner, count_decisions

log = logging.getLogger("lantern.planner")


def _scenario_context(scenario_id: str, sim_hour: int) -> tuple[str, dict]:
    """(hazard, weather row for sim_hour) from raw/ files. Never reads truth/."""
    events = []
    try:
        events = store.get_json(f"raw/scenarios/{scenario_id}/events.json")
    except KeyError:
        pass
    hazard = next((e["hazard"] for e in events if e.get("type") == "hazard_start"), None)
    if hazard is None:
        parts = scenario_id.split("_")
        hazard = parts[0] if parts[0] in ("wildfire", "flood", "power") else (parts[1] if len(parts) > 1 else "wildfire")
        hazard = "power_loss" if hazard == "power" else hazard
    weather = {}
    for w in store.get_jsonl(f"raw/scenarios/{scenario_id}/weather.jsonl"):
        if int(w["sim_hour"]) <= sim_hour:
            weather = w
    return hazard, weather


def data_loss_pct(inventory: list[InventoryState]) -> float:
    sites = {r.site_id for r in inventory}
    stale = {r.site_id for r in inventory if r.data_status == "stale"}
    return round(100.0 * len(stale) / len(sites), 1) if sites else 0.0


def run_plan(
    scenario_id: str,
    sim_hour: int,
    planner: str,
    session_id: str,
    apply_gate: bool = True,
) -> Plan:
    t0 = time.perf_counter()
    planner = Planner(planner).value
    pid = make_plan_id(scenario_id, planner, sim_hour)

    # 1. load
    rows = store.query_pk(settings.table_inventory, scenario_id)
    if not rows:
        raise ValueError(f"no inventory for {scenario_id}; reset and step the scenario first")
    inventory = [InventoryState(**r) for r in rows]
    sites = {s["site_id"]: s for s in store.query_pk(settings.table_sites, scenario_id)}

    # 2-3. estimate + forecast
    inventory = estimator.estimate(inventory)
    hazard, weather = _scenario_context(scenario_id, sim_hour)
    inventory = forecaster.apply_forecast(
        inventory, {k: v["site_type"] for k, v in sites.items()}, hazard, weather
    )

    # 4. propose
    result = None
    if planner == Planner.equal_split.value:
        from baselines.equal_split import propose as equal_split

        transfers = equal_split(inventory, sim_hour, pid)
    else:
        result = optimizer.propose(inventory, sites, pid, "robust" if planner == "lantern" else "naive")
        transfers = result.transfers

    # 5. gate
    if apply_gate:
        from gate.gate import evaluate_transfers

        transfers = evaluate_transfers(session_id, transfers, inventory, session_aware=True)

    # 6. scouts
    scouts = []
    if planner == Planner.lantern.value and result is not None:
        scouts = scout.pick_scouts(inventory, sites, result, pid)

    plan = Plan(
        scenario_id=scenario_id, plan_id=pid, session_id=session_id, planner=planner,
        sim_hour=sim_hour, data_loss_pct=data_loss_pct(inventory), apply_gate=apply_gate,
        transfers=transfers, scouts=scouts, counts=count_decisions(transfers),
        created_at=iso(),
    )

    # 7. explain (M4) - never loses the plan
    try:
        from explain.bedrock_explain import explain_plan

        plan = explain_plan(plan)
    except Exception:  # noqa: BLE001
        log.exception("explain_plan failed; keeping plan without explanation")

    # 8. save
    plan = plan.model_copy(update={"runtime_ms": int((time.perf_counter() - t0) * 1000)})
    store.put_item(settings.table_plans, plan.to_item())
    store.batch_put(settings.table_inventory, [r.to_item() for r in inventory])

    # 9. alert + fallback (M4) - lantern only, off during eval
    if planner == Planner.lantern.value and settings.notify_enabled:
        try:
            from alerts.fallback_publish import write_fallback
            from alerts.sns_alerts import publish_plan

            publish_plan(plan)
            write_fallback(plan)
        except Exception:  # noqa: BLE001
            log.exception("alerts failed; plan is saved")
    return plan
