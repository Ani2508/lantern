"""Fixtures and config must match the shared contract. OWNER: M1."""

from __future__ import annotations

import json
import re
from pathlib import Path

from lantern_core.config import REPO_ROOT, Settings, settings
from lantern_core.schemas import Event, Plan, Report, Site, TruthStockRow, WeatherRow

FIX = REPO_ROOT / "tests" / "fixtures" / "wildfire_demo_01"


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def test_sites_validate():
    sites = [Site(**s) for s in json.loads((FIX / "sites.json").read_text())]
    assert [s.site_id for s in sites] == ["S01", "S02", "S03", "S04", "S05"]


def test_reports_validate_and_dark_sites_are_silent():
    for h in range(10):
        reports = [Report(**r) for r in _jsonl(FIX / "reports" / f"h{h:03d}.jsonl")]
        sites = {r.site_id for r in reports}
        if h >= 3:
            assert "S02" not in sites and "S04" not in sites
        else:
            assert len(sites) == 5


def test_plan_fixtures_validate():
    for name in ("plan_naive_h009.json", "plan_lantern_h009.json"):
        plan = Plan(**json.loads((FIX / name).read_text()))
        assert plan.plan_id == f"plan_wildfire_demo_01_{plan.planner}_h009"
        for t in plan.transfers:
            assert t.transfer_id.startswith(plan.plan_id + "_t")


def test_resource_names_use_prefix():
    for name in (settings.table_sites, settings.table_inventory, settings.table_plans,
                 settings.table_gate_log, settings.fn_simulate, settings.fn_ingest, settings.fn_plan):
        assert name.startswith("lantern-dev-")


def test_env_example_keys_exist_in_settings():
    fields = {f.upper() for f in Settings.model_fields}
    keys = re.findall(r"^([A-Z_0-9]+)=", (REPO_ROOT / ".env.example").read_text(), re.M)
    missing = [k for k in keys if k not in fields and not k.startswith("VITE_")]
    assert not missing, f".env.example keys not in Settings: {missing}"


def test_engine_never_reads_truth():
    for p in (REPO_ROOT / "engine").glob("*.py"):
        assert "truth/scenarios" not in p.read_text(), f"{p.name} reads truth/"


def test_raw_files_validate():
    for e in json.loads((FIX / "events.json").read_text()):
        Event(**e)
    for w in _jsonl(FIX / "weather.jsonl"):
        WeatherRow(**w)
    for t in _jsonl(FIX / "truth" / "stock.jsonl"):
        TruthStockRow(**t)
