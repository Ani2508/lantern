from datetime import UTC, datetime

import pytest

from lantern_core import ids


def test_scenario_ids_roundtrip():
    assert ids.train_scenario_id("flood", 1003) == "train_flood_1003"
    assert ids.test_scenario_id("power_loss", 2001) == "test_power_loss_2001"
    assert ids.eval_scenario_id("wildfire", 40, 7) == "eval_wildfire_l40_0007"
    assert ids.parse_scenario_id("eval_wildfire_l40_0007") == {
        "kind": "eval",
        "hazard": "wildfire",
        "data_loss_pct": 40,
        "seed": 7,
    }
    assert ids.parse_scenario_id("test_power_loss_2001")["hazard"] == "power_loss"
    assert ids.parse_scenario_id("wildfire_demo_01")["kind"] == "demo"
    with pytest.raises(ValueError):
        ids.parse_scenario_id("nope")


def test_session_plan_transfer_scout():
    now = datetime(2026, 11, 7, 8, 0, 0, tzinfo=UTC)
    assert ids.session_id("wildfire_demo_01", "lantern", now) == "sess_wildfire_demo_01_lantern_20261107T080000"
    pid = ids.plan_id("wildfire_demo_01", "naive", 9)
    assert pid == "plan_wildfire_demo_01_naive_h009"
    assert ids.transfer_id(pid, 3) == "plan_wildfire_demo_01_naive_h009_t03"
    assert ids.scout_id("plan_wildfire_demo_01_lantern_h009", 1) == "plan_wildfire_demo_01_lantern_h009_s01"


def test_parse_plan_id_handles_underscored_planner():
    assert ids.parse_plan_id("plan_eval_flood_l10_0003_equal_split_h012") == {
        "scenario_id": "eval_flood_l10_0003",
        "planner": "equal_split",
        "sim_hour": 12,
    }
    with pytest.raises(ValueError):
        ids.parse_plan_id("plan_x_badplanner_h001")


def test_site_supply_and_field_report():
    assert ids.site_supply("S04", "insulin") == "S04#insulin"
    assert ids.parse_site_supply("S04#insulin") == ("S04", "insulin")
    with pytest.raises(ValueError):
        ids.parse_site_supply("S04")
    assert ids.field_report_id("wildfire_demo_01", 9, 1) == "fr_wildfire_demo_01_h009_01"
