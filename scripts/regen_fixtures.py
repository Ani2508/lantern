"""Rebuild plan_*_h009.json from the real code and copy mocks into the dashboard."""

from __future__ import annotations

import json
import shutil

from api.demo_story import mode, run_story, write_json
from lantern_core.config import DEMO_SCENARIO_ID, ROOT_DIR

FIXTURE = ROOT_DIR / "tests" / "fixtures" / DEMO_SCENARIO_ID
MOCKS = ROOT_DIR / "dashboard" / "src" / "mocks"
PUBLIC_FALLBACK = ROOT_DIR / "dashboard" / "public" / "fallback"
STABLE = {
    "created_at": "2026-11-07T17:00:00Z",
    "runtime_ms": 12.0,
    "session_id": None,  # filled per planner
}


def _stable(plan, session_id: str) -> dict:
    item = plan.to_item()
    item["created_at"] = STABLE["created_at"]
    item["runtime_ms"] = STABLE["runtime_ms"]
    item["session_id"] = session_id
    return item


def _hourly_story(to_hour: int = 9) -> dict:
    """States for every hour of the time-lapse, the naive single-transfer check, and the events."""
    from api import service

    service.reset_scenario(DEMO_SCENARIO_ID)
    states = []
    for h in range(to_hour + 1):
        if h:
            service.step_scenario(DEMO_SCENARIO_ID, h)
        st = service.get_state(DEMO_SCENARIO_ID)
        states.append({**st, "latest_plans": {}, "sessions": {}})
    naive = service.make_plan(DEMO_SCENARIO_ID, "naive", apply_gate=True)
    return {
        "states": states,
        "single_check": service.single_transfer_check(naive.plan_id),
        "events": service.scenario_events(DEMO_SCENARIO_ID),
    }


def main() -> None:
    with mode("memory"):
        story = run_story()
    with mode("memory"):
        hourly = _hourly_story()
    naive_sid = "sess_wildfire_demo_01_naive_20261107T080000"
    lantern_sid = "sess_wildfire_demo_01_lantern_20261107T080000"
    write_json(FIXTURE / "plan_naive_h009.json", _stable(story["plan_naive"], naive_sid))
    write_json(FIXTURE / "plan_lantern_h009.json", _stable(story["plan_lantern"], lantern_sid))

    MOCKS.mkdir(parents=True, exist_ok=True)
    for name in ("plan_naive_h009.json", "plan_lantern_h009.json"):
        shutil.copyfile(FIXTURE / name, MOCKS / name)
    write_json(MOCKS / "state_h000.json", story["state_h000"])
    write_json(MOCKS / "state_h009.json", story["state_before_plans"])
    write_json(MOCKS / "state_after_report.json", story["state_after_report"])
    write_json(MOCKS / "plan_lantern_after_report.json", _stable(story["plan_lantern_after_report"], lantern_sid + "b"))
    write_json(MOCKS / "field_reports.json", json.loads((FIXTURE / "field_reports.json").read_text(encoding="utf-8")))
    write_json(MOCKS / "gate_log_naive.json", story["gate_log_naive"])
    write_json(MOCKS / "state_hours.json", hourly["states"])
    write_json(MOCKS / "single_check_naive.json", hourly["single_check"])
    write_json(MOCKS / "events.json", hourly["events"])
    # Prefer the real eval results (python scripts/tasks.py eval); placeholder only if none exist yet.
    from api import service

    chart = service.proof_chart()
    if not chart["rows"]:
        chart = {
            "rows": [
                {"planner": "equal_split", "data_loss_pct": 0, "seed": 0, "shortage_hours": 12, "unmet_demand_units": 40},
                {"planner": "equal_split", "data_loss_pct": 40, "seed": 0, "shortage_hours": 40, "unmet_demand_units": 90},
                {"planner": "naive", "data_loss_pct": 0, "seed": 0, "shortage_hours": 10, "unmet_demand_units": 30},
                {"planner": "naive", "data_loss_pct": 40, "seed": 0, "shortage_hours": 36, "unmet_demand_units": 80},
                {"planner": "lantern", "data_loss_pct": 0, "seed": 0, "shortage_hours": 8, "unmet_demand_units": 20},
                {"planner": "lantern", "data_loss_pct": 40, "seed": 0, "shortage_hours": 18, "unmet_demand_units": 35},
            ],
            "summary": {
                "shortage_hours_mean": {
                    "equal_split": {"0": 12, "40": 40},
                    "naive": {"0": 10, "40": 36},
                    "lantern": {"0": 8, "40": 18},
                },
                "unsafe_caught_session": 4,
                "unsafe_caught_single": 1,
                "unsafe_total": 5,
                "interval_coverage_90": 0.86,
                "replan_seconds_p50": 0.04,
            },
        }
    write_json(MOCKS / "proof_chart.json", chart)
    shutil.copyfile(FIXTURE / "sites.json", MOCKS / "sites.json")

    html = ROOT_DIR / "web" / "fallback" / "index.html"
    if html.exists():
        PUBLIC_FALLBACK.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(html, PUBLIC_FALLBACK / "index.html")
        from alerts.fallback_publish import build_payload

        PUBLIC_FALLBACK.joinpath("plan.json").write_text(
            json.dumps(build_payload(story["plan_lantern"], story["state_before_plans"]["sites"]), indent=1),
            encoding="utf-8",
        )
    print(f"fixtures written to {FIXTURE} and {MOCKS}")


if __name__ == "__main__":
    main()
