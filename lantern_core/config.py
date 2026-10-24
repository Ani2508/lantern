"""Single source of configuration for every Lantern module (contract 2.4 and 2.8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent

BANNER = "SIMULATED DATA · synthetic scenario for demonstration only"
PLANNER_NAMES = {
    "equal_split": "Equal split",
    "naive": "Naive AI (trusts old data)",
    "lantern": "Lantern",
}
DEMO_SCENARIO_ID = "wildfire_demo_01"
SUPPLY_ORDER = ("water", "food", "insulin")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # contract 2.4
    LANTERN_ENV: str = "dev"
    LANTERN_MODE: Literal["local", "aws", "memory"] = "local"
    AWS_REGION: str = "us-east-1"
    AWS_PROFILE: str = "lantern"
    ACCOUNT_ID: str = "000000000000"
    PREFIX: str = "lantern-dev"
    DATA_BUCKET: str = "lantern-dev-data-${ACCOUNT_ID}"
    WEB_BUCKET: str = "lantern-dev-web-${ACCOUNT_ID}"
    TABLE_SITES: str = "lantern-dev-sites"
    TABLE_INVENTORY: str = "lantern-dev-inventory"
    TABLE_PLANS: str = "lantern-dev-plans"
    TABLE_GATE_LOG: str = "lantern-dev-gate-log"
    FN_SIMULATE: str = "lantern-dev-simulate"
    FN_INGEST: str = "lantern-dev-ingest"
    FN_PLAN: str = "lantern-dev-plan"
    SNS_TOPIC_ARN: str = "arn:aws:sns:us-east-1:${ACCOUNT_ID}:lantern-dev-alerts"
    BEDROCK_ENABLED: bool = False
    BEDROCK_MODEL_ID: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    BEDROCK_FALLBACK_MODEL_ID: str = "us.amazon.nova-lite-v1:0"
    BEDROCK_TIMEOUT_S: float = 8
    # LLM switch: BEDROCK_ENABLED turns LLM text on; LLM_PROVIDER picks who writes it.
    # "ollama" runs a local model (dev laptop); "bedrock" uses the BEDROCK_* model ids above.
    LLM_PROVIDER: Literal["bedrock", "ollama"] = "bedrock"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_FALLBACK_MODEL: str = "llama3.1:8b"
    OLLAMA_TIMEOUT_S: float = 30
    OLLAMA_KEEP_ALIVE: str = "1h"
    NOTIFY_ENABLED: bool = False
    FORECASTER_MODEL_KEY: str = "models/forecaster/v1/model.json"
    FORECASTER_MODE: Literal["auto", "heuristic"] = "auto"
    LOCAL_STORE_DIR: str = "./.localstore"
    SIM_START_TS: str = "2026-11-07T08:00:00Z"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    FALLBACK_PUBLIC_URL: str = ""
    FIELD_REPORT_MIN_CONFIDENCE: float = 0.7
    VITE_API_BASE_URL: str = "http://localhost:8000/api"
    VITE_USE_MOCKS: bool = True

    # contract 2.8
    PLAN_HORIZON_H: int = 72
    QUANTILES: Annotated[list[float], NoDecode] = [0.05, 0.5, 0.95]
    STALE_SIGMA_FRAC: float = 0.35
    STALE_QTY_FRAC: float = 0.04
    Z_90: float = 1.645
    MAX_TRANSFERS_PER_PLAN: int = 10
    SCOUT_MAX_PER_PLAN: int = 2
    REPLAN_EVERY_H: int = 6
    GATE_SOURCE_RESERVE_H: float = 24
    GATE_SOURCE_RESERVE_H_CRITICAL: float = 72
    GATE_DEST_MIN_H: float = 12
    GATE_MAX_TRANSFER_FRAC: float = 0.5
    GATE_SESSION_DRAW_FRAC: float = 0.6
    GATE_SESSION_REVIEW_FRAC: float = 0.8
    GATE_STALE_REVIEW_H: float = 6
    DATA_LOSS_LEVELS: Annotated[list[int], NoDecode] = [0, 10, 20, 30, 40, 50, 60, 70]
    EVAL_SEEDS: int = 20

    # supplies (contract 2.5)
    SUPPLIES: dict[str, dict[str, Any]] = {
        "water": {"unit": "gallon", "usage_per_person_per_day": 1.0, "critical": False},
        "food": {"unit": "meal", "usage_per_person_per_day": 3.0, "critical": False},
        "insulin": {"unit": "vial", "usage_per_person_per_day": 0.01, "critical": True},
    }
    TRANSFER_CAP: dict[str, float] = {"water": 300, "food": 600, "insulin": 6}
    MIN_TRANSFER_QTY: dict[str, float] = {"water": 25, "food": 50, "insulin": 2}

    @field_validator("QUANTILES", "DATA_LOSS_LEVELS", "CORS_ORIGINS", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    @model_validator(mode="after")
    def _expand_account_id(self) -> Settings:
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, str) and "${ACCOUNT_ID}" in value:
                object.__setattr__(self, name, value.replace("${ACCOUNT_ID}", self.ACCOUNT_ID))
        return self

    # helpers
    def usage_per_h(self, supply_id: str) -> float:
        return float(self.SUPPLIES[supply_id]["usage_per_person_per_day"]) / 24.0

    def is_critical(self, supply_id: str) -> bool:
        return bool(self.SUPPLIES[supply_id]["critical"])

    def unit(self, supply_id: str) -> str:
        return str(self.SUPPLIES[supply_id]["unit"])

    def reserve_hours(self, supply_id: str) -> float:
        return self.GATE_SOURCE_RESERVE_H_CRITICAL if self.is_critical(supply_id) else self.GATE_SOURCE_RESERVE_H

    @property
    def llm_model_ids(self) -> list[str]:
        """Primary then fallback model for the active LLM_PROVIDER."""
        if self.LLM_PROVIDER == "ollama":
            pair = (self.OLLAMA_MODEL, self.OLLAMA_FALLBACK_MODEL)
        else:
            pair = (self.BEDROCK_MODEL_ID, self.BEDROCK_FALLBACK_MODEL_ID)
        return [m for m in pair if m]

    @property
    def local_store_path(self) -> Path:
        p = Path(self.LOCAL_STORE_DIR)
        return p if p.is_absolute() else (ROOT_DIR / p)

    def sim_hour_to_iso(self, h: int) -> str:
        return sim_hour_to_iso(h, self.SIM_START_TS)


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def sim_hour_to_iso(h: int, start_ts: str | None = None) -> str:
    start = _parse_iso(start_ts or settings.SIM_START_TS)
    return (start + timedelta(hours=int(h))).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


settings = Settings()
