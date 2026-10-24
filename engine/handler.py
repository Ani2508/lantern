"""Lambda-style plan handler: {scenario_id, sim_hour, planner, session_id, apply_gate} -> Plan dict."""

from __future__ import annotations

from engine.planner import run_plan


def handler(event: dict, context=None) -> dict:
    plan = run_plan(
        event["scenario_id"],
        int(event["sim_hour"]),
        event["planner"],
        event["session_id"],
        bool(event.get("apply_gate", True)),
    )
    return plan.to_item()
