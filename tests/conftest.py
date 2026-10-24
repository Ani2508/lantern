"""Every test runs against a fresh local store in a temp folder."""

from __future__ import annotations

import pytest

from lantern_core.config import settings


@pytest.fixture(autouse=True)
def local_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "lantern_mode", "local")
    monkeypatch.setattr(settings, "local_store_dir", str(tmp_path / "store"))
    monkeypatch.setattr(settings, "notify_enabled", False)
    monkeypatch.setattr(settings, "bedrock_enabled", False)
    from engine import forecaster

    forecaster.reload_model()
    yield tmp_path / "store"
    forecaster.reload_model()


@pytest.fixture
def demo_at_hour_9():
    from simulator.run import reset, step

    reset("wildfire_demo_01")
    step("wildfire_demo_01", 9)
    return "wildfire_demo_01"
