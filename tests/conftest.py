from __future__ import annotations

from pathlib import Path

import pytest

from lantern_core import store
from lantern_core.config import settings

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "wildfire_demo_01"
REPO_ROOT = Path(__file__).resolve().parent.parent

_OVERRIDES = {
    "LANTERN_MODE": "memory",
    "BEDROCK_ENABLED": False,
    "LLM_PROVIDER": "bedrock",
    "NOTIFY_ENABLED": False,
    "FORECASTER_MODE": "heuristic",
}


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    from explain import bedrock_client, bedrock_explain

    for k, v in _OVERRIDES.items():
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "LOCAL_STORE_DIR", str(tmp_path / "localstore"))
    store.reset_memory()
    store.clear_cache()
    bedrock_explain.clear_cache()
    bedrock_client.set_client(None)
    yield
    store.reset_memory()
    store.clear_cache()
    bedrock_explain.clear_cache()
    bedrock_client.set_client(None)


DEMO = "wildfire_demo_01"


@pytest.fixture
def demo_h9():
    """Demo scenario stepped to hour 9 in memory: (estimated inventory rows by site_supply, sites)."""
    from engine.estimator import estimate
    from simulator import run

    run.reset(DEMO)
    run.step(DEMO, 9)
    rows = estimate(store.query_pk(settings.TABLE_INVENTORY, DEMO))
    sites = store.query_pk(settings.TABLE_SITES, DEMO)
    return {r["site_supply"]: r for r in rows}, sites
