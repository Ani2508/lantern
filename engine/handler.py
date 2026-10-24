"""Lambda handler for lantern-dev-plan. OWNER: M3.

event: {"scenario_id", "sim_hour", "planner", "session_id", "apply_gate"?}
returns: the Plan as JSON (contract 2.7).
"""

from __future__ import annotations

from engine.planner import run_plan


def lambda_handler(event, _context):
    plan = run_plan(
        scenario_id=event["scenario_id"],
        sim_hour=int(event["sim_hour"]),
        planner=event["planner"],
        session_id=event["session_id"],
        apply_gate=bool(event.get("apply_gate", True)),
    )
    return plan.to_item()
