"""ID builders (contract 2.5). OWNER: M1. Never format an id by hand elsewhere."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def scenario_id(kind: str, hazard: str | None = None, seed: int | None = None, loss_pct: int | None = None) -> str:
    """kind = 'demo' | 'train' | 'test' | 'eval'.

    scenario_id("demo")                         -> wildfire_demo_01
    scenario_id("train", "flood", 12)           -> train_flood_0012
    scenario_id("eval", "wildfire", 7, 40)      -> eval_wildfire_l40_0007
    """
    if kind == "demo":
        return "wildfire_demo_01"
    if kind in ("train", "test"):
        return f"{kind}_{hazard}_{seed:04d}"
    if kind == "eval":
        return f"eval_{hazard}_l{loss_pct:02d}_{seed:04d}"
    raise ValueError(f"unknown scenario kind: {kind}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(ts: datetime | None = None) -> str:
    """ISO 8601 UTC ending in Z."""
    ts = ts or utc_now()
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sim_time(sim_start_ts: str, sim_hour: int) -> datetime:
    start = datetime.strptime(sim_start_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return start + timedelta(hours=sim_hour)


def session_id(scenario: str, planner: str, ts: datetime | None = None) -> str:
    ts = ts or utc_now()
    return f"sess_{scenario}_{planner}_{ts.strftime('%Y%m%dT%H%M%S')}"


def plan_id(scenario: str, planner: str, sim_hour: int) -> str:
    return f"plan_{scenario}_{planner}_h{sim_hour:03d}"


def transfer_id(plan: str, n: int) -> str:
    return f"{plan}_t{n:02d}"


def scout_id(plan: str, n: int) -> str:
    return f"{plan}_s{n:02d}"


def site_supply(site: str, supply: str) -> str:
    return f"{site}#{supply}"


def report_key(scenario: str, sim_hour: int) -> str:
    return f"raw/scenarios/{scenario}/reports/h{sim_hour:03d}.jsonl"
