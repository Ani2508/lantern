"""Single source of configuration for every Lantern module (contract 2.4 + 2.8).

OWNER: M1. Every bucket, table, topic, function and model name is read from
`settings`; nothing else in the repo hardcodes them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- 2.4 environment -------------------------------------------------
    lantern_env: str = "dev"
    lantern_mode: Literal["local", "memory", "aws"] = "local"
    aws_region: str = "us-east-1"
    aws_profile: str | None = "lantern"
    account_id: str = "000000000000"
    prefix: str = "lantern-dev"
    data_bucket: str = ""
    web_bucket: str = ""
    table_sites: str = "lantern-dev-sites"
    table_inventory: str = "lantern-dev-inventory"
    table_plans: str = "lantern-dev-plans"
    table_gate_log: str = "lantern-dev-gate-log"
    fn_simulate: str = "lantern-dev-simulate"
    fn_ingest: str = "lantern-dev-ingest"
    fn_plan: str = "lantern-dev-plan"
    sns_topic_arn: str = ""
    bedrock_enabled: bool = True
    notify_enabled: bool = True  # v1.2: SMS + fallback page; eval sets false
    fallback_url: str = ""  # public URL of the fallback page, appended to SMS (M4)
    cors_origins: str = "http://localhost:5173"  # comma-separated; add the CloudFront URL (M1)
    bedrock_model_id: str = ""
    bedrock_timeout_s: int = 8
    forecaster_model_key: str = "models/forecaster/v1/model.json"
    local_store_dir: str = "./.localstore"
    sim_start_ts: str = "2026-11-07T08:00:00Z"

    # --- 2.8 engine and gate parameters ----------------------------------
    plan_horizon_h: int = 72
    quantiles: tuple[float, float, float] = (0.05, 0.5, 0.95)
    stale_sigma_frac: float = 0.35
    # v1.2: uncertainty also grows with the size of the last count
    stale_qty_frac: float = 0.04
    z_90: float = 1.645
    max_transfers_per_plan: int = 10
    # v1.2: largest single load per supply (insulin = one cooler box)
    transfer_unit_cap: dict[str, float] = {"water": 500, "food": 1500, "insulin": 6}
    scout_max_per_plan: int = 2
    replan_every_h: int = 6
    gate_source_reserve_h: float = 24
    gate_source_reserve_h_critical: float = 72
    gate_dest_min_h: float = 12
    gate_max_transfer_frac: float = 0.5
    gate_session_draw_frac: float = 0.6
    gate_session_review_frac: float = 0.8
    gate_stale_review_h: float = 6
    data_loss_levels: tuple[int, ...] = (0, 10, 20, 30, 40, 50, 60, 70)
    eval_seeds: int = 20

    @model_validator(mode="after")
    def _derive_names(self) -> Settings:
        # Fill names that depend on ACCOUNT_ID when .env left them unset or
        # unexpanded (e.g. "lantern-dev-data-${ACCOUNT_ID}").
        def unresolved(v: str) -> bool:
            return not v or "${" in v

        if unresolved(self.data_bucket):
            self.data_bucket = f"{self.prefix}-data-{self.account_id}"
        if unresolved(self.web_bucket):
            self.web_bucket = f"{self.prefix}-web-{self.account_id}"
        if unresolved(self.sns_topic_arn):
            self.sns_topic_arn = (
                f"arn:aws:sns:{self.aws_region}:{self.account_id}:{self.prefix}-alerts"
            )
        if self.bedrock_model_id.startswith("<"):
            self.bedrock_model_id = ""
        return self

    @property
    def store_path(self) -> Path:
        p = Path(self.local_store_dir)
        return p if p.is_absolute() else REPO_ROOT / p


settings = Settings()
