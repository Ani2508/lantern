"""ID builders and parsers (contract 2.5)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_PLANNERS = "equal_split|naive|lantern"
_PLAN_RE = re.compile(rf"^plan_(?P<scenario_id>.+)_(?P<planner>{_PLANNERS})_h(?P<sim_hour>\d{{3}})$")
_SCENARIO_RE = re.compile(
    r"^(?:(?P<kind>train|test)_(?P<hazard>wildfire|flood|power_loss)_(?P<seed>\d{4})"
    r"|eval_(?P<ehazard>wildfire|flood|power_loss)_l(?P<loss>\d{2})_(?P<eseed>\d{4}))$"
)


def demo_scenario_id() -> str:
    return "wildfire_demo_01"


def train_scenario_id(hazard: str, seed: int) -> str:
    return f"train_{hazard}_{seed:04d}"


def test_scenario_id(hazard: str, seed: int) -> str:
    return f"test_{hazard}_{seed:04d}"


test_scenario_id.__test__ = False  # not a pytest test


def eval_scenario_id(hazard: str, loss_pct: int, seed: int) -> str:
    return f"eval_{hazard}_l{loss_pct:02d}_{seed:04d}"


def parse_scenario_id(scenario_id: str) -> dict:
    """Return {kind, hazard, data_loss_pct, seed}; data_loss_pct is None unless it is in the id."""
    if scenario_id == demo_scenario_id():
        return {"kind": "demo", "hazard": "wildfire", "data_loss_pct": 40, "seed": None}
    m = _SCENARIO_RE.match(scenario_id)
    if not m:
        raise ValueError(f"unknown scenario_id {scenario_id!r}")
    if m.group("kind"):
        return {"kind": m.group("kind"), "hazard": m.group("hazard"), "data_loss_pct": None, "seed": int(m.group("seed"))}
    return {
        "kind": "eval",
        "hazard": m.group("ehazard"),
        "data_loss_pct": int(m.group("loss")),
        "seed": int(m.group("eseed")),
    }


def session_id(scenario_id: str, planner: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"sess_{scenario_id}_{planner}_{now.strftime('%Y%m%dT%H%M%S')}"


def plan_id(scenario_id: str, planner: str, sim_hour: int) -> str:
    return f"plan_{scenario_id}_{planner}_h{int(sim_hour):03d}"


def parse_plan_id(pid: str) -> dict:
    m = _PLAN_RE.match(pid)
    if not m:
        raise ValueError(f"bad plan_id {pid!r}")
    return {"scenario_id": m.group("scenario_id"), "planner": m.group("planner"), "sim_hour": int(m.group("sim_hour"))}


def transfer_id(pid: str, n: int) -> str:
    return f"{pid}_t{int(n):02d}"


def scout_id(pid: str, n: int) -> str:
    return f"{pid}_s{int(n):02d}"


def site_supply(site_id: str, supply_id: str) -> str:
    return f"{site_id}#{supply_id}"


def parse_site_supply(value: str) -> tuple[str, str]:
    site, sep, supply = value.partition("#")
    if not sep or not site or not supply:
        raise ValueError(f"bad site_supply {value!r}")
    return site, supply


def field_report_id(scenario_id: str, sim_hour: int, n: int) -> str:
    return f"fr_{scenario_id}_h{int(sim_hour):03d}_{int(n):02d}"
