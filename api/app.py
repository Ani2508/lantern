"""FastAPI + Mangum: every route in extras/plans/02_contract_v1.2.md section 2.10."""

from __future__ import annotations

import logging
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from pydantic import BaseModel, ConfigDict, Field

from api import service
from lantern_core.config import BANNER, PLANNER_NAMES, settings
from lantern_core.schemas import PlannerName, SupplyId

log = logging.getLogger(__name__)

app = FastAPI(title="Lantern", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_local_llm() -> None:
    """Ollama takes ~20 s to load a model cold; load it in the background so the demo click is fast."""
    if not (settings.BEDROCK_ENABLED and settings.LLM_PROVIDER == "ollama" and settings.LANTERN_MODE != "memory"):
        return

    def _run() -> None:
        from explain import bedrock_client

        try:
            model, secs = bedrock_client.warm()
            log.info("warmed ollama model %s in %.1fs", model, secs)
        except Exception as e:  # the template fallback still works
            log.warning("ollama warm-up failed: %s", e)

    threading.Thread(target=_run, daemon=True).start()


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepBody(_Body):
    to_hour: int


class PlanBody(_Body):
    planner: PlannerName
    apply_gate: bool = True


class FieldReportBody(_Body):
    text: str


class ConfirmBody(_Body):
    field_report_id: str
    site_id: str
    supply_id: SupplyId
    qty: float = Field(ge=0)


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


@app.exception_handler(service.ServiceError)
async def _service_error(_request: Request, exc: service.ServiceError) -> JSONResponse:
    return _err(exc.status, exc.code, exc.message)


@app.exception_handler(Exception)
async def _internal(_request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error")
    return _err(500, "internal", str(exc))


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mode": settings.LANTERN_MODE}


@app.get("/api/config/public")
def config_public() -> dict:
    return {
        "banner": BANNER,
        "planner_names": PLANNER_NAMES,
        "bedrock_enabled": settings.BEDROCK_ENABLED,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.llm_model_ids[0] if settings.llm_model_ids else "",
        "notify_enabled": settings.NOTIFY_ENABLED,
        "mode": settings.LANTERN_MODE,
    }


@app.get("/api/scenarios")
def scenarios() -> list[str]:
    return service.list_scenarios()


@app.post("/api/scenarios/{scenario_id}/reset")
def reset(scenario_id: str) -> dict:
    return {"sim_hour": service.reset_scenario(scenario_id).sim_hour}


@app.post("/api/scenarios/{scenario_id}/step")
def step(scenario_id: str, body: StepBody) -> dict:
    return {"sim_hour": service.step_scenario(scenario_id, body.to_hour).sim_hour}


@app.get("/api/scenarios/{scenario_id}/state")
def state(scenario_id: str) -> dict:
    return service.get_state(scenario_id)


@app.post("/api/scenarios/{scenario_id}/plan")
def plan(scenario_id: str, body: PlanBody) -> dict:
    return service.make_plan(scenario_id, body.planner, body.apply_gate).to_item()


@app.get("/api/plans/{plan_id}")
def get_plan(plan_id: str) -> dict:
    return service.get_plan(plan_id).to_item()


@app.get("/api/plans/{plan_id}/single-check")
def single_check(plan_id: str) -> list[dict]:
    """The same transfers checked one at a time (session_aware=False), for the pitch contrast."""
    return service.single_transfer_check(plan_id)


@app.get("/api/scenarios/{scenario_id}/events")
def events(scenario_id: str) -> list[dict]:
    return service.scenario_events(scenario_id)


@app.get("/api/sessions/{session_id}/gate-log")
def gate_log(session_id: str) -> list[dict]:
    return service.gate_log(session_id)


@app.get("/api/eval/proof-chart")
def proof_chart() -> dict:
    return service.proof_chart()


@app.post("/api/scenarios/{scenario_id}/field-report")
def field_report(scenario_id: str, body: FieldReportBody) -> dict:
    return service.field_report(scenario_id, body.text).to_item()


@app.post("/api/scenarios/{scenario_id}/field-report/confirm")
def confirm_field_report(scenario_id: str, body: ConfirmBody) -> dict:
    return service.confirm_field_report(scenario_id, body.field_report_id, body.site_id, body.supply_id, body.qty)


handler = Mangum(app)
