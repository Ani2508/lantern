"""Scenario operations shared by the API, the local demo and the scripts."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

from engine.estimator import estimate, estimate_row
from engine.planner import run_plan
from explain.field_report import audit_key, parse_field_report
from gate import gate
from ingest.handler import ingest_report
from lantern_core import ids, store
from lantern_core.config import DEMO_SCENARIO_ID, settings, utc_now_iso
from lantern_core.schemas import PLANNERS, FieldReportParse, InventoryState, Plan, Report, RunState, Transfer
from simulator import generator as sim_generator
from simulator import run as sim


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def run_state_key(scenario_id: str) -> str:
    return f"state/scenarios/{scenario_id}/run.json"


def load_run_state(scenario_id: str) -> RunState | None:
    raw = store.get_json(run_state_key(scenario_id))
    return RunState.model_validate(raw) if raw else None


def save_run_state(rs: RunState) -> None:
    store.put_json(run_state_key(rs.scenario_id), rs.to_item())


def _require_state(scenario_id: str) -> RunState:
    rs = load_run_state(scenario_id)
    if rs is None:
        raise ServiceError(409, "conflict", f"scenario {scenario_id} has not been reset")
    return rs


def new_session_id(scenario_id: str, planner: str, taken: set[str]) -> str:
    now = datetime.now(UTC)
    sid = ids.session_id(scenario_id, planner, now)
    while sid in taken:
        now += timedelta(seconds=1)
        sid = ids.session_id(scenario_id, planner, now)
    return sid


def _check_scenario(scenario_id: str) -> None:
    try:
        ids.parse_scenario_id(scenario_id)
    except ValueError as e:
        raise ServiceError(404, "not_found", str(e)) from e


def list_scenarios() -> list[str]:
    found = {DEMO_SCENARIO_ID}
    for k in store.list_keys("raw/scenarios/"):
        parts = k.split("/")
        if len(parts) > 3:
            found.add(parts[2])
    return sorted(found, key=lambda s: (s != DEMO_SCENARIO_ID, s))


def reset_scenario(scenario_id: str) -> RunState:
    _check_scenario(scenario_id)
    sim.reset(scenario_id)
    old = load_run_state(scenario_id)
    taken = set(old.sessions.values()) if old else set()
    rs = RunState(
        scenario_id=scenario_id,
        sim_hour=0,
        sessions={p: new_session_id(scenario_id, p, taken) for p in PLANNERS},
    )
    save_run_state(rs)
    return rs


def step_scenario(scenario_id: str, to_hour: int) -> RunState:
    rs = _require_state(scenario_id)
    try:
        sim.step(scenario_id, int(to_hour))
    except ValueError as e:
        raise ServiceError(400, "bad_request", str(e)) from e
    rs = rs.model_copy(update={"sim_hour": int(to_hour)})
    save_run_state(rs)
    return rs


def _inventory_view(scenario_id: str) -> list[dict]:
    """Inventory with current estimates (stored model tts kept when the stored estimate is current)."""
    out = []
    for stored in store.query_pk(settings.TABLE_INVENTORY, scenario_id):
        fresh = estimate_row(stored)
        if stored.get("est_qty_p50") is not None and abs(float(stored["est_qty_p50"]) - fresh["est_qty_p50"]) < 0.01:
            for k in ("tts_p05_h", "tts_p50_h", "tts_p95_h"):
                if stored.get(k) is not None:
                    fresh[k] = stored[k]
        out.append(InventoryState.model_validate(fresh).to_item())
    return out


def get_state(scenario_id: str) -> dict:
    _check_scenario(scenario_id)
    rs = load_run_state(scenario_id)
    sites = store.query_pk(settings.TABLE_SITES, scenario_id)
    inventory = _inventory_view(scenario_id)
    sim_hour = rs.sim_hour if rs else max((r["sim_hour"] for r in inventory), default=0)
    sessions = rs.sessions if rs else {}
    latest: dict[str, dict] = {}
    current = set(sessions.values())
    for p in store.query_pk(settings.TABLE_PLANS, scenario_id):
        if p.get("session_id") not in current or p["sim_hour"] > sim_hour:
            continue
        prev = latest.get(p["planner"])
        if prev is None or (p["sim_hour"], p.get("created_at", "")) >= (prev["sim_hour"], prev.get("created_at", "")):
            latest[p["planner"]] = p
    return {"sim_hour": sim_hour, "sites": sites, "inventory": inventory, "latest_plans": latest, "sessions": sessions}


def make_plan(scenario_id: str, planner: str, apply_gate: bool = True) -> Plan:
    if planner not in PLANNERS:
        raise ServiceError(400, "bad_request", f"unknown planner {planner!r}")
    rs = _require_state(scenario_id)
    session = rs.sessions.get(planner)
    if not session:
        session = new_session_id(scenario_id, planner, set(rs.sessions.values()))
        rs = rs.model_copy(update={"sessions": {**rs.sessions, planner: session}})
        save_run_state(rs)
    return run_plan(scenario_id, rs.sim_hour, planner, session, apply_gate)


def get_plan(plan_id: str) -> Plan:
    try:
        info = ids.parse_plan_id(plan_id)
    except ValueError as e:
        raise ServiceError(400, "bad_request", str(e)) from e
    item = store.get_item(settings.TABLE_PLANS, info["scenario_id"], plan_id)
    if item is None:
        raise ServiceError(404, "not_found", f"plan {plan_id} not found")
    return Plan.model_validate(item)


def gate_log(session_id: str) -> list[dict]:
    return store.query_pk(settings.TABLE_GATE_LOG, session_id)


def single_transfer_check(plan_id: str) -> list[dict]:
    """The same transfers through the gate with session_aware=False (nothing is logged)."""
    plan = get_plan(plan_id)
    if not plan.transfers:
        return []
    inventory = estimate(store.query_pk(settings.TABLE_INVENTORY, plan.scenario_id))
    bare = [Transfer.model_validate({k: v for k, v in t.to_item().items() if k in ("transfer_id", "plan_id", "source_site_id", "dest_site_id", "supply_id", "qty", "priority_rank", "distance_km")}) for t in plan.transfers]
    checked = gate.evaluate_transfers(plan.session_id, bare, inventory, session_aware=False, write_log=False)
    return [{"transfer_id": t.transfer_id, "decision": t.decision, "rule_hits": t.rule_hits, "reason_text": t.reason_text} for t in checked]


def scenario_events(scenario_id: str) -> list[dict]:
    """The scenario's events.json (hazard, site_dark, evacuee_arrival, ...), sorted by hour."""
    _check_scenario(scenario_id)
    events = store.get_json(f"{sim_generator.raw_prefix(scenario_id)}/events.json")
    if events is None:
        events = sim_generator.build(scenario_id).events
    return sorted(events, key=lambda e: e.get("sim_hour", 0))


def field_report(scenario_id: str, text: str) -> FieldReportParse:
    if not text or not text.strip():
        raise ServiceError(400, "bad_request", "text is required")
    _require_state(scenario_id)
    return parse_field_report(scenario_id, text.strip())


def confirm_field_report(scenario_id: str, field_report_id: str, site_id: str, supply_id: str, qty: float) -> dict:
    rs = _require_state(scenario_id)
    audit = store.get_json(audit_key(scenario_id, field_report_id))
    if audit is None:
        raise ServiceError(404, "not_found", f"field report {field_report_id} not found")
    row = store.get_item(settings.TABLE_INVENTORY, scenario_id, ids.site_supply(site_id, supply_id or ""))
    if row is None:
        raise ServiceError(400, "bad_request", f"unknown site or supply: {site_id} {supply_id}")
    if qty is None or float(qty) < 0:
        raise ServiceError(400, "bad_request", "qty must be zero or more")
    report = Report(
        scenario_id=scenario_id,
        sim_hour=rs.sim_hour,
        site_id=site_id,
        supply_id=supply_id,
        qty=float(qty),
        people_served=int(row["people_served"]),
    )
    ingest_report(report)
    fresh = estimate_row(store.get_item(settings.TABLE_INVENTORY, scenario_id, ids.site_supply(site_id, supply_id)))
    store.put_item(settings.TABLE_INVENTORY, InventoryState.model_validate(fresh).to_item())
    session = new_session_id(scenario_id, "lantern", set(rs.sessions.values()))
    rs = rs.model_copy(update={"sessions": {**rs.sessions, "lantern": session}})
    save_run_state(rs)
    store.put_json(
        audit_key(scenario_id, field_report_id),
        {**audit, "confirmed": {"site_id": site_id, "supply_id": supply_id, "qty": float(qty), "at": utc_now_iso()}},
    )
    return {
        "sim_hour": rs.sim_hour,
        "inventory_row": InventoryState.model_validate(fresh).to_item(),
        "session_id": session,
    }


def _read_csv(key: str) -> list[dict]:
    text = store.get_text(key)
    if not text:
        return []
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append({k: (float(v) if k not in ("planner",) else v) for k, v in r.items()})
    return rows


def proof_chart() -> dict:
    rows = _read_csv("eval/results/proof_chart.csv")
    for r in rows:
        r["data_loss_pct"] = int(r["data_loss_pct"])
        r["seed"] = int(r["seed"])
    return {"rows": rows, "summary": store.get_json("eval/results/summary.json", default={}), "sensitivity": _read_csv("eval/results/sensitivity.csv")}
