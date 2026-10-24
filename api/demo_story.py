"""The hour-9 demo story (01 section 5), shared by local_demo, regen-fixtures, fallback and tests."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

from api import service
from lantern_core import store
from lantern_core.config import DEMO_SCENARIO_ID, ROOT_DIR, settings

FIELD_REPORTS = json.loads(
    (ROOT_DIR / "tests" / "fixtures" / DEMO_SCENARIO_ID / "field_reports.json").read_text(encoding="utf-8")
)


@contextlib.contextmanager
def mode(name: str):
    """Temporarily switch LANTERN_MODE (memory runs start from an empty store)."""
    old = settings.LANTERN_MODE
    settings.LANTERN_MODE = name
    if name == "memory":
        store.reset_memory()
    try:
        yield
    finally:
        settings.LANTERN_MODE = old


def run_story(scenario_id: str = DEMO_SCENARIO_ID, to_hour: int = 9, with_field_report: bool = True) -> dict:
    """Run steps 1-5b against the current store and return every intermediate result."""
    out: dict = {}
    service.reset_scenario(scenario_id)
    out["state_h000"] = service.get_state(scenario_id)
    service.step_scenario(scenario_id, to_hour)
    out["state_before_plans"] = service.get_state(scenario_id)

    naive = service.make_plan(scenario_id, "naive", apply_gate=True)
    out["plan_naive"] = naive
    out["single_transfer_check"] = service.single_transfer_check(naive.plan_id)
    out["gate_log_naive"] = service.gate_log(naive.session_id)

    lantern = service.make_plan(scenario_id, "lantern", apply_gate=True)
    out["plan_lantern"] = lantern
    out["gate_log_lantern"] = service.gate_log(lantern.session_id)
    out["state_after_plans"] = service.get_state(scenario_id)

    if with_field_report:
        parses = [service.field_report(scenario_id, fr["text"]) for fr in FIELD_REPORTS]
        out["field_report_parses"] = parses
        p = parses[0]
        out["confirm"] = service.confirm_field_report(scenario_id, p.field_report_id, p.site_id, p.supply_id, p.qty)
        replan = service.make_plan(scenario_id, "lantern", apply_gate=True)
        out["plan_lantern_after_report"] = replan
        out["gate_log_lantern_after_report"] = service.gate_log(replan.session_id)
        out["state_after_report"] = service.get_state(scenario_id)
    out["run_state"] = service.load_run_state(scenario_id)
    return out


def hour9_lantern_in_memory():
    """(lantern plan, sites) for the demo at hour 9, computed in a throwaway memory store."""
    with mode("memory"):
        story = run_story(with_field_report=False)
        sites = store.query_pk(settings.TABLE_SITES, DEMO_SCENARIO_ID)
    return story["plan_lantern"], sites


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(obj, "to_item"):
        obj = obj.to_item()
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
