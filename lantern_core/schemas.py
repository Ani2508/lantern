"""Shared data objects (contract 2.7). Every model forbids extra fields."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SiteType = Literal["shelter", "clinic", "pharmacy", "food_bank"]
Hazard = Literal["wildfire", "flood", "power_loss"]
PlannerName = Literal["equal_split", "naive", "lantern"]
Decision = Literal["APPROVE", "REVIEW", "BLOCK"]
DataStatus = Literal["live", "stale"]
ExplanationSource = Literal["bedrock", "template"]
RuleId = Literal["R1_SOURCE_RESERVE", "R2_DEST_MIN_HOURS", "R3_MAX_SIZE", "R4_SESSION_DRAW", "R5_STALE_SOURCE"]
ParserSource = Literal["bedrock", "rules"]
EventType = Literal["hazard_start", "site_dark", "evacuee_arrival", "demand_spike", "delivery"]
SupplyId = Literal["water", "food", "insulin"]

SITE_TYPES: tuple[str, ...] = ("shelter", "clinic", "pharmacy", "food_bank")
HAZARDS: tuple[str, ...] = ("wildfire", "flood", "power_loss")
PLANNERS: tuple[str, ...] = ("equal_split", "naive", "lantern")
DECISIONS: tuple[str, ...] = ("APPROVE", "REVIEW", "BLOCK")
RULE_IDS: tuple[str, ...] = (
    "R1_SOURCE_RESERVE",
    "R2_DEST_MIN_HOURS",
    "R3_MAX_SIZE",
    "R4_SESSION_DRAW",
    "R5_STALE_SOURCE",
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_item(self) -> dict:
        """Dict for storage: None values dropped (missing values are omitted, never null)."""
        return self.model_dump(mode="json", exclude_none=True)


def status_for_age(report_age_h: float) -> str:
    return "live" if report_age_h < 1 else "stale"


class Site(_Model):
    scenario_id: str
    site_id: str
    name: str
    site_type: SiteType
    lat: float
    lon: float
    people_served: int
    created_at: str


class Report(_Model):
    scenario_id: str
    sim_hour: int
    site_id: str
    supply_id: SupplyId
    qty: float = Field(ge=0)
    people_served: int


class InventoryState(_Model):
    scenario_id: str
    site_supply: str
    site_id: str
    supply_id: SupplyId
    sim_hour: int
    last_reported_qty: float
    last_report_hour: int
    report_age_h: float
    data_status: DataStatus
    people_served: int
    burn_rate_per_h: float | None = None
    est_qty_p05: float | None = None
    est_qty_p50: float | None = None
    est_qty_p95: float | None = None
    tts_p05_h: float | None = None
    tts_p50_h: float | None = None
    tts_p95_h: float | None = None
    updated_at: str | None = None

    @model_validator(mode="after")
    def _check(self) -> InventoryState:
        if self.site_supply != f"{self.site_id}#{self.supply_id}":
            raise ValueError(f"site_supply {self.site_supply!r} must equal site_id#supply_id")
        if self.data_status != status_for_age(self.report_age_h):
            raise ValueError(f"data_status {self.data_status!r} does not match report_age_h {self.report_age_h}")
        return self


class Transfer(_Model):
    transfer_id: str
    plan_id: str
    source_site_id: str
    dest_site_id: str
    supply_id: SupplyId
    qty: float = Field(gt=0)
    priority_rank: int
    distance_km: float
    decision: Decision | None = None
    rule_hits: list[RuleId] = Field(default_factory=list)
    reason_text: str | None = None
    explanation_text: str | None = None


class ScoutVisit(_Model):
    scout_id: str
    site_id: str
    supply_ids: list[SupplyId]
    voi_score: float
    reason_text: str


class Counts(_Model):
    approve: int = 0
    review: int = 0
    block: int = 0


class Plan(_Model):
    scenario_id: str
    plan_id: str
    session_id: str
    planner: PlannerName
    sim_hour: int
    data_loss_pct: float
    apply_gate: bool
    transfers: list[Transfer] = Field(default_factory=list)
    scouts: list[ScoutVisit] = Field(default_factory=list)
    counts: Counts = Field(default_factory=Counts)
    summary_text: str = ""
    explanation_source: ExplanationSource = "template"
    runtime_ms: float = 0
    created_at: str


class GateLogRow(_Model):
    session_id: str
    transfer_id: str
    plan_id: str
    scenario_id: str
    planner: PlannerName
    source_site_id: str
    dest_site_id: str
    supply_id: SupplyId
    qty: float
    decision: Decision
    rule_hits: list[RuleId] = Field(default_factory=list)
    reason_text: str
    source_p05_before: float
    source_p05_after: float
    cumulative_draw_qty: float
    cumulative_draw_limit: float
    source_report_age_h: float
    dest_tts_p05_h_after: float
    created_at: str


class Event(_Model):
    sim_hour: int
    type: EventType
    hazard: Hazard | None = None
    site_ids: list[str] | None = None
    site_id: str | None = None
    people: int | None = None
    supply_id: SupplyId | None = None
    extra_qty: float | None = None
    over_hours: int | None = None


class Weather(_Model):
    sim_hour: int
    temp_c: float
    hazard_level: int = Field(ge=0, le=3)


class TruthStock(_Model):
    scenario_id: str
    sim_hour: int
    site_id: str
    supply_id: SupplyId
    qty: float = Field(ge=0)
    demand: float = Field(ge=0)
    unmet: float = Field(ge=0)


class FieldReportParse(_Model):
    field_report_id: str
    scenario_id: str
    sim_hour: int
    source_text: str
    site_id: str | None = None
    supply_id: SupplyId | None = None
    qty: float | None = None
    confidence: float = Field(ge=0, le=1)
    notes: str = ""
    parser_source: ParserSource
    needs_confirmation: bool
    problems: list[str] = Field(default_factory=list)


class RunState(_Model):
    scenario_id: str
    sim_hour: int
    sessions: dict[PlannerName, str] = Field(default_factory=dict)
