"""Lantern API (contract 2.10). OWNER: M1.  DRAFT by M3 for M1 review.

Local mode calls the modules in-process. AWS mode invokes lantern-dev-simulate
and lantern-dev-plan synchronously and reads tables directly.
Sessions: `reset` starts a new gate session per planner; the plan route passes
that session_id into run_plan (agreed M1 + M3).

    make api   ->  http://localhost:8000/api/health
"""

from __future__ import annotations

import io
import json

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lantern_core import store
from lantern_core.config import REPO_ROOT, settings
from lantern_core.ids import session_id as make_session_id
from lantern_core.schemas import Planner

app = FastAPI(title="Lantern API", version="1.2")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
api = APIRouter(prefix="/api")

PLANNERS = [p.value for p in Planner]


class StepBody(BaseModel):
    to_hour: int


class PlanBody(BaseModel):
    planner: Planner = Planner.lantern
    apply_gate: bool = True


@app.exception_handler(HTTPException)
async def _http_error(_req, exc: HTTPException):
    code, _, msg = str(exc.detail).partition(": ")
    return JSONResponse(status_code=exc.status_code, content={"error": code, "message": msg or code})


@app.exception_handler(Exception)
async def _any_error(_req, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "internal", "message": str(exc)})


# --- helpers ----------------------------------------------------------------
def _aws() -> bool:
    return settings.lantern_mode == "aws"


def _invoke(function: str, payload: dict) -> dict:
    import boto3

    resp = boto3.client("lambda", region_name=settings.aws_region).invoke(
        FunctionName=function, InvocationType="RequestResponse", Payload=json.dumps(payload).encode()
    )
    body = json.loads(resp["Payload"].read() or b"{}")
    if resp.get("FunctionError"):
        raise HTTPException(502, f"lambda_error: {body.get('errorMessage', 'failed')}")
    return body


def _sessions_key(scenario_id: str) -> str:
    return f"state/sessions/{scenario_id}.json"


def _new_sessions(scenario_id: str) -> dict:
    sessions = {p: make_session_id(scenario_id, p) for p in PLANNERS}
    store.put_json(_sessions_key(scenario_id), sessions)
    return sessions


def _session_for(scenario_id: str, planner: str) -> str:
    try:
        return store.get_json(_sessions_key(scenario_id))[planner]
    except (KeyError, TypeError):
        return _new_sessions(scenario_id)[planner]


def _scenario_of(plan_id: str) -> str:
    for p in PLANNERS:
        marker = f"_{p}_h"
        if marker in plan_id:
            return plan_id[len("plan_") : plan_id.index(marker)]
    raise HTTPException(400, "bad_plan_id: expected plan_<scenario>_<planner>_hNNN")


# --- routes (contract 2.10) ---------------------------------------------------
@api.get("/health")
def health():
    return {"ok": True, "mode": settings.lantern_mode}


@api.get("/scenarios")
def scenarios():
    found = {p.name for p in (REPO_ROOT / "tests" / "fixtures").iterdir() if p.is_dir()} if not _aws() else set()
    for k in store.list_keys("raw/scenarios/"):
        found.add(k.split("/")[2])
    return sorted(found)


@api.post("/scenarios/{scenario_id}/reset")
def reset(scenario_id: str):
    if _aws():
        out = _invoke(settings.fn_simulate, {"action": "reset", "scenario_id": scenario_id})
    else:
        from simulator.run import reset as sim_reset

        out = {"sim_hour": sim_reset(scenario_id)}
    _new_sessions(scenario_id)
    return out


@api.post("/scenarios/{scenario_id}/step")
def step(scenario_id: str, body: StepBody):
    if _aws():
        return _invoke(settings.fn_simulate, {"action": "step", "scenario_id": scenario_id, "to_hour": body.to_hour})
    from simulator.run import current_hour
    from simulator.run import step as sim_step

    try:
        sim_step(scenario_id, body.to_hour)
    except ValueError as e:
        raise HTTPException(400, f"bad_hour: {e}") from e
    return {"sim_hour": current_hour(scenario_id)}


@api.get("/scenarios/{scenario_id}/state")
def state(scenario_id: str):
    sites = store.query_pk(settings.table_sites, scenario_id)
    inventory = store.query_pk(settings.table_inventory, scenario_id)
    if not sites:
        raise HTTPException(404, f"not_found: reset {scenario_id} first")
    return {"sim_hour": max((int(r["sim_hour"]) for r in inventory), default=0),
            "sites": sites, "inventory": inventory}


@api.post("/scenarios/{scenario_id}/plan")
def plan(scenario_id: str, body: PlanBody):
    inventory = store.query_pk(settings.table_inventory, scenario_id)
    if not inventory:
        raise HTTPException(404, f"not_found: reset {scenario_id} first")
    sim_hour = max(int(r["sim_hour"]) for r in inventory)
    planner = body.planner.value
    event = {"scenario_id": scenario_id, "sim_hour": sim_hour, "planner": planner,
             "session_id": _session_for(scenario_id, planner), "apply_gate": body.apply_gate}
    if _aws():
        return _invoke(settings.fn_plan, event)
    from engine.handler import lambda_handler

    return lambda_handler(event, None)


@api.get("/plans/{plan_id}")
def get_plan(plan_id: str):
    item = store.get_item(settings.table_plans, {"scenario_id": _scenario_of(plan_id), "plan_id": plan_id})
    if not item:
        raise HTTPException(404, f"not_found: {plan_id}")
    return item


@api.get("/sessions/{session_id}/gate-log")
def gate_log(session_id: str):
    return store.query_pk(settings.table_gate_log, session_id)


@api.get("/eval/proof-chart")
def proof_chart():
    import csv

    try:
        text = store.get_object("eval/results/proof_chart.csv").decode()
        rows = [{k: (float(v) if k in ("shortage_hours", "unmet_demand_units") else int(v) if k in ("data_loss_pct", "seed") else v)
                 for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
        summary = store.get_json("eval/results/summary.json")
    except KeyError as e:
        raise HTTPException(404, "not_found: run make eval first") from e
    return {"rows": rows, "summary": summary}


app.include_router(api)


def handler(event, context):
    """lantern-dev-api entry point (Lambda Function URL)."""
    from mangum import Mangum

    return Mangum(app, lifespan="off")(event, context)
