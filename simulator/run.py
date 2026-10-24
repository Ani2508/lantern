"""Simulation driver: reset and step a scenario through the store, then ingest each hour."""

from __future__ import annotations

import json

from ingest.handler import process_hour
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import Report
from simulator import generator
from simulator.generator import build, raw_prefix, truth_key


def sim_state_key(scenario_id: str) -> str:
    return f"state/scenarios/{scenario_id}/sim.json"


def load_sim_state(scenario_id: str) -> dict | None:
    return store.get_json(sim_state_key(scenario_id))


def _save_sim_state(scenario_id: str, state: dict) -> None:
    store.put_json(sim_state_key(scenario_id), state)


def _write_sites_table(spec: generator.ScenarioSpec, h: int) -> None:
    store.batch_put(settings.TABLE_SITES, generator.sites_at_hour(spec, h))


def reset(scenario_id: str) -> int:
    """Write the static files and sites table, clear the run state, ingest hour 0. Returns 0."""
    spec = build(scenario_id)
    generator.write_static_files(spec)
    _write_sites_table(spec, 0)
    truth, lines = generator.initial_truth(spec)
    text = "".join(json.dumps(r) + "\n" for r in lines)
    store.put_object(truth_key(scenario_id), text)
    store.put_jsonl(f"{raw_prefix(scenario_id)}/reports/h000.jsonl", generator.reports_for_hour(spec, 0, truth))
    _save_sim_state(scenario_id, {"sim_hour": 0, "truth": truth, "pending_transfers": [], "executed": []})
    process_hour(scenario_id, 0, reset=True)
    return 0


def step(scenario_id: str, to_hour: int) -> list[Report]:
    """Advance hour by hour to `to_hour`, writing reports and truth through the store, then ingesting."""
    spec = build(scenario_id)
    state = load_sim_state(scenario_id)
    if state is None:
        reset(scenario_id)
        state = load_sim_state(scenario_id)
    to_hour = int(to_hour)
    if to_hour > spec.horizon_h:
        raise ValueError(f"to_hour {to_hour} is past the {spec.horizon_h} h horizon")
    if to_hour < state["sim_hour"]:
        raise ValueError(f"cannot step back from hour {state['sim_hour']} to {to_hour}")

    truth = state["truth"]
    produced: list[Report] = []
    new_truth_text = []
    for h in range(state["sim_hour"] + 1, to_hour + 1):
        pending = [t for t in state["pending_transfers"] if t["apply_hour"] == h]
        state["pending_transfers"] = [t for t in state["pending_transfers"] if t["apply_hour"] != h]
        truth, lines, executed = generator.step_truth(spec, h, truth, pending)
        state["executed"].extend({**t, "apply_hour": h} for t in executed)
        reports = generator.reports_for_hour(spec, h, truth)
        store.put_jsonl(f"{raw_prefix(scenario_id)}/reports/h{h:03d}.jsonl", reports)
        new_truth_text.extend(json.dumps(r) + "\n" for r in lines)
        if h > 0 and (spec.people[h] != spec.people[h - 1]).any():
            _write_sites_table(spec, h)
        process_hour(scenario_id, h)
        produced.extend(Report.model_validate(r) for r in reports)
    if new_truth_text:
        old = store.get_text(truth_key(scenario_id)) or ""
        store.put_object(truth_key(scenario_id), old + "".join(new_truth_text))
    state["sim_hour"] = to_hour
    state["truth"] = truth
    _save_sim_state(scenario_id, state)
    return produced


def apply_transfers(scenario_id: str, transfers: list) -> None:
    """Queue executed transfers; they move true stock at the next simulated hour."""
    state = load_sim_state(scenario_id)
    if state is None:
        raise ValueError(f"scenario {scenario_id} has not been reset")
    for t in transfers:
        d = t.model_dump() if hasattr(t, "model_dump") else dict(t)
        state["pending_transfers"].append(
            {
                "transfer_id": d.get("transfer_id"),
                "source_site_id": d["source_site_id"],
                "dest_site_id": d["dest_site_id"],
                "supply_id": d["supply_id"],
                "qty": float(d["qty"]),
                "apply_hour": state["sim_hour"] + 1,
            }
        )
    _save_sim_state(scenario_id, state)


def current_hour(scenario_id: str) -> int | None:
    state = load_sim_state(scenario_id)
    return None if state is None else int(state["sim_hour"])


def handler(event: dict, context=None) -> dict:
    action = event.get("action")
    if action == "reset":
        return {"sim_hour": reset(event["scenario_id"])}
    if action == "step":
        step(event["scenario_id"], int(event["to_hour"]))
        return {"sim_hour": int(event["to_hour"])}
    raise ValueError(f"unknown action {action!r}")
