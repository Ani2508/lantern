"""The hour-9 demo story. OWNERS: M3 + M4. Must stay green until the demo.

Skipped while gate/gate.py is still M4's stub. Asserts decisions and rule ids,
not exact quantities (agreed with M2 for v1.2).
"""

from __future__ import annotations

import pytest

import gate.gate as gate_module
from engine.planner import run_plan

pytestmark = pytest.mark.skipif(getattr(gate_module, "IS_STUB", False), reason="waiting for M4's real gate")


def test_naive_is_blocked_on_pharmacy_insulin(demo_at_hour_9):
    plan = run_plan(demo_at_hour_9, 9, "naive", "sess_story_naive")
    s04 = [t for t in plan.transfers if t.source_site_id == "S04" and t.supply_id == "insulin"]
    assert [t.decision for t in s04[:3]] == ["REVIEW", "REVIEW", "BLOCK"]
    assert "R5_STALE_SOURCE" in s04[0].rule_hits
    assert "R4_SESSION_DRAW" in s04[2].rule_hits
    assert any("R1_SOURCE_RESERVE" in t.rule_hits for t in s04)


def test_lantern_has_no_blocks_and_scouts_the_pharmacy(demo_at_hour_9):
    plan = run_plan(demo_at_hour_9, 9, "lantern", "sess_story_lantern")
    assert plan.counts.block == 0
    assert len(plan.scouts) == 2
    assert "S04" in {s.site_id for s in plan.scouts}
