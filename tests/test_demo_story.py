import pytest

from api.demo_story import run_story

TOL = 0.05


@pytest.fixture
def story():
    return run_story()


def test_naive_with_gate_blocks_s04_insulin(story):
    naive = story["plan_naive"]
    assert naive.data_loss_pct == 40
    assert [t.decision for t in naive.transfers] == ["REVIEW", "REVIEW", "BLOCK"]
    blocks = [t for t in naive.transfers if t.decision == "BLOCK"]
    assert any(t.source_site_id == "S04" and t.supply_id == "insulin" for t in blocks)
    assert naive.counts.model_dump() == {"approve": 0, "review": 2, "block": 1}
    assert naive.explanation_source == "template"
    assert [c["decision"] for c in story["single_transfer_check"]] == ["REVIEW"] * 3


def test_lantern_zero_block_two_scouts(story):
    lantern = story["plan_lantern"]
    assert lantern.counts.block == 0
    assert [t.decision for t in lantern.transfers] == ["APPROVE"] * 3
    assert all(t.source_site_id == "S03" and t.qty == 6 for t in lantern.transfers)
    assert len(lantern.scouts) == 2
    assert {s.site_id for s in lantern.scouts} == {"S04", "S02"}
    s04 = next(s for s in lantern.scouts if s.site_id == "S04")
    s02 = next(s for s in lantern.scouts if s.site_id == "S02")
    assert s04.reason_text == "Insulin at Central Pharmacy is somewhere between 21 and 58 vials; a count changes the plan."
    assert s02.reason_text.startswith("Insulin at Shelter B is somewhere between 0.1 and 1.4 vials;")
    assert s04.supply_ids[0] == "insulin"
    assert lantern.explanation_source == "template" and lantern.summary_text
    assert all(t.explanation_text for t in lantern.transfers)


def test_field_report_changes_the_plan(story):
    p1, p2 = story["field_report_parses"]
    assert (p1.site_id, p1.supply_id, p1.qty, p1.parser_source) == ("S04", "insulin", 19, "rules")
    assert not p1.needs_confirmation
    assert (p2.site_id, p2.supply_id, p2.qty) == ("S02", "insulin", 1)
    assert p2.needs_confirmation and "Low confidence" in p2.notes
    row = story["confirm"]["inventory_row"]
    assert row["data_status"] == "live" and row["est_qty_p05"] == row["est_qty_p95"] == 19
    replan = story["plan_lantern_after_report"]
    assert replan.session_id == story["confirm"]["session_id"] != story["plan_lantern"].session_id
    assert replan.counts.block == 0
    from_s04 = [t.qty for t in replan.transfers if t.source_site_id == "S04"]
    assert from_s04 == [6, pytest.approx(3.11, abs=TOL)]
    assert {t.source_site_id for t in replan.transfers} == {"S03", "S04"}
    state = story["state_after_report"]
    s04 = {r["supply_id"]: r for r in state["inventory"] if r["site_id"] == "S04"}
    assert s04["insulin"]["data_status"] == "live" and s04["water"]["data_status"] == "stale"


def test_state_has_latest_plans_and_sessions(story):
    st = story["state_after_plans"]
    assert st["sim_hour"] == 9
    assert set(st["latest_plans"]) == {"naive", "lantern"}
    assert set(st["sessions"]) == {"equal_split", "naive", "lantern"}
    assert len(st["sites"]) == 5 and len(st["inventory"]) == 15
