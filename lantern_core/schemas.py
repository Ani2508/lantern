"""Shared data objects and enums (contract 2.5 - 2.7).

OWNER: M1. Field names here are the contract. Changing one is a contract
change: agree it in the team channel and bump the contract version first.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# --- 2.5 enums (exact strings) ---------------------------------------------
class SiteType(str, Enum):
    shelter = "shelter"
    clinic = "clinic"
    pharmacy = "pharmacy"
    food_bank = "food_bank"


class Hazard(str, Enum):
    wildfire = "wildfire"
    flood = "flood"
    power_loss = "power_loss"


class Planner(str, Enum):
    equal_split = "equal_split"
    naive = "naive"
    lantern = "lantern"


class Decision(str, Enum):
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class DataStatus(str, Enum):
    live = "live"  # report_age_h < 1
    stale = "stale"  # report_age_h >= 1


class ExplanationSource(str, Enum):
    bedrock = "bedrock"
    template = "template"


# --- 2.5 supplies ------------------------------------------------------------
class SupplySpec(BaseModel):
    supply_id: str
    unit: str
    usage_per_person_per_day: float
    critical: bool


SUPPLIES: dict[str, SupplySpec] = {
    "water": SupplySpec(supply_id="water", unit="gallon", usage_per_person_per_day=1.0, critical=False),
    "food": SupplySpec(supply_id="food", unit="meal", usage_per_person_per_day=3.0, critical=False),
    # v1.2 synthetic assumption, labelled on screen: ~10% diabetic, 1 vial ~ 10 days
    "insulin": SupplySpec(supply_id="insulin", unit="vial", usage_per_person_per_day=0.01, critical=True),
}


# Which supplies each site type consumes (agreed M2 + M3; v1.2).
SITE_SUPPLIES: dict[str, set[str]] = {
    "shelter": {"water", "food", "insulin"},
    "clinic": {"water", "food", "insulin"},
    "pharmacy": {"insulin"},
    "food_bank": {"water", "food"},
}


# --- 2.6 / 2.7 objects -------------------------------------------------------
class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    def to_item(self) -> dict:
        """Dict ready for the store: enums as strings, None values dropped."""
        return self.model_dump(mode="json", exclude_none=True)


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
    supply_id: str
    qty: float
    people_served: int


class InventoryState(_Model):
    # report fields (writer: M2)
    scenario_id: str
    site_supply: str
    site_id: str
    supply_id: str
    sim_hour: int
    last_reported_qty: float
    last_report_hour: int
    report_age_h: float
    data_status: DataStatus
    people_served: int
    # estimate and forecast fields (writer: M3)
    burn_rate_per_h: float | None = None
    est_qty_p05: float | None = None
    est_qty_p50: float | None = None
    est_qty_p95: float | None = None
    tts_p05_h: float | None = None
    tts_p50_h: float | None = None
    tts_p95_h: float | None = None
    updated_at: str


class Transfer(_Model):
    # filled by the optimizer
    transfer_id: str
    plan_id: str
    source_site_id: str
    dest_site_id: str
    supply_id: str
    qty: float
    priority_rank: int
    distance_km: float
    # added by the gate
    decision: Decision | None = None
    rule_hits: list[str] = Field(default_factory=list)
    reason_text: str | None = None
    # added by explain
    explanation_text: str | None = None


class ScoutVisit(_Model):
    scout_id: str
    site_id: str
    supply_ids: list[str]
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
    planner: Planner
    sim_hour: int
    data_loss_pct: float
    apply_gate: bool
    transfers: list[Transfer] = Field(default_factory=list)
    scouts: list[ScoutVisit] = Field(default_factory=list)
    counts: Counts = Field(default_factory=Counts)
    summary_text: str = ""
    explanation_source: ExplanationSource = ExplanationSource.template
    runtime_ms: int = 0
    created_at: str


class GateLogRow(_Model):
    session_id: str
    transfer_id: str
    plan_id: str
    scenario_id: str
    planner: Planner
    source_site_id: str
    dest_site_id: str
    supply_id: str
    qty: float
    decision: Decision
    rule_hits: list[str] = Field(default_factory=list)
    reason_text: str = ""
    source_p05_before: float | None = None
    source_p05_after: float | None = None
    cumulative_draw_qty: float | None = None
    cumulative_draw_limit: float | None = None
    source_report_age_h: float | None = None
    dest_tts_p05_after_h: float | None = None
    created_at: str


def count_decisions(transfers: list[Transfer]) -> Counts:
    c = Counts()
    for t in transfers:
        if t.decision == Decision.APPROVE.value:
            c.approve += 1
        elif t.decision == Decision.REVIEW.value:
            c.review += 1
        elif t.decision == Decision.BLOCK.value:
            c.block += 1
    return c


# --- raw scenario files (Dataset doc section 6) -------------------------------
class Event(_Model):
    sim_hour: int
    type: str  # hazard_start | site_dark | evacuee_arrival | demand_spike | delivery
    hazard: Hazard | None = None
    site_id: str | None = None
    site_ids: list[str] | None = None
    people: int | None = None
    supply_id: str | None = None
    extra_qty: float | None = None
    over_hours: int | None = None
    qty: float | None = None


class WeatherRow(_Model):
    sim_hour: int
    temp_c: float
    hazard_level: int


class TruthStockRow(_Model):
    scenario_id: str
    sim_hour: int
    site_id: str
    supply_id: str
    qty: float
    demand: float
    unmet: float
