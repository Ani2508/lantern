"""Generated scenarios. OWNER: M2.  DRAFT by M3 for M2 review."""

from __future__ import annotations

from simulator.features import scenario_rows
from simulator.run import max_hour, reset, step
from simulator.world import World, dark_count, parse


def test_parse_ids():
    s = parse("eval_power_loss_l40_0007")
    assert (s.kind, s.hazard, s.loss_pct, s.seed) == ("eval", "power_loss", 40, 7)
    assert parse("train_flood_0012").hazard == "flood"


def test_same_seed_same_world():
    a, b = World("train_wildfire_0003"), World("train_wildfire_0003")
    ra, rb = [], []
    for _ in range(24):
        ra += a.reports()
        a.advance()
        rb += b.reports()
        b.advance()
    assert ra == rb


def test_dark_sites_go_silent_and_truth_never_negative():
    w = World("eval_wildfire_l40_0001")
    assert len(w.dark) == dark_count(40) == 2
    for _ in range(w.hours):
        reporting = {r["site_id"] for r in w.reports()}
        if w.hour >= w.hazard_start:
            assert not (reporting & w.dark)
        for row in w.advance():
            assert row["qty"] >= 0 and row["demand"] >= 0


def test_generated_scenario_runs_through_reset_and_step():
    reset("test_flood_0002")
    assert max_hour("test_flood_0002") == 71
    assert step("test_flood_0002", 12)


def test_features_use_estimated_stock_not_truth():
    rows = scenario_rows("train_wildfire_0005")
    assert rows and all(0 <= r["target_tts_h"] <= 72 for r in rows)
    stale = [r for r in rows if r["report_age_h"] > 0]
    assert stale, "expected some stale rows"
