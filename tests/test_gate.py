import pytest

from engine.optimizer import propose
from gate import rules
from gate.gate import evaluate_transfers
from lantern_core import store
from lantern_core.config import settings
from lantern_core.schemas import Transfer

TOL = 0.05
SESSION = "sess_wildfire_demo_01_naive_20261107T080000"


# ---- each rule on its own


def test_r1():
    assert rules.r1_source_reserve(21.14, 18, 4.5) == ("R1_SOURCE_RESERVE", "BLOCK")
    assert rules.r1_source_reserve(21.14, 12, 4.5) is None


def test_r2():
    assert rules.r2_dest_min_hours(11.9) == ("R2_DEST_MIN_HOURS", "REVIEW")
    assert rules.r2_dest_min_hours(12.0) is None


def test_r3():
    assert rules.r3_max_size(10.6, 21.14) == ("R3_MAX_SIZE", "BLOCK")
    assert rules.r3_max_size(10.5, 21.14) is None


def test_r4_strict_bands():
    limit = 0.6 * 21.14
    assert rules.r4_session_draw(limit, 21.14) == ("R4_SESSION_DRAW", "REVIEW")
    assert rules.r4_session_draw(limit + 0.01, 21.14) == ("R4_SESSION_DRAW", "BLOCK")
    assert rules.r4_session_draw(0.8 * limit, 21.14) is None
    assert rules.r4_session_draw(0.8 * limit + 0.01, 21.14) == ("R4_SESSION_DRAW", "REVIEW")


def test_r5():
    assert rules.r5_stale_source(7) == ("R5_STALE_SOURCE", "REVIEW")
    assert rules.r5_stale_source(6) is None


def test_precedence():
    assert rules.combine([("R5_STALE_SOURCE", "REVIEW"), ("R3_MAX_SIZE", "BLOCK")]) == "BLOCK"
    assert rules.combine([("R5_STALE_SOURCE", "REVIEW"), None]) == "REVIEW"
    assert rules.combine([None, None]) == "APPROVE"


# ---- the demo case


def _naive(demo_h9):
    rows, sites = demo_h9
    return propose(list(rows.values()), sites, "naive", "plan_wildfire_demo_01_naive_h009"), rows, sites


def test_demo_review_review_block(demo_h9):
    ts, rows, sites = _naive(demo_h9)
    out = evaluate_transfers(SESSION, ts, list(rows.values()), sites=sites)
    assert [t.decision for t in out] == ["REVIEW", "REVIEW", "BLOCK"]
    assert out[0].rule_hits == ["R5_STALE_SOURCE"]
    assert out[1].rule_hits == ["R4_SESSION_DRAW", "R5_STALE_SOURCE"]
    assert out[2].rule_hits == ["R1_SOURCE_RESERVE", "R4_SESSION_DRAW", "R5_STALE_SOURCE"]
    assert out[2].reason_text == (
        "Central Pharmacy would fall below its 72 h insulin reserve. 3 transfers from Central Pharmacy "
        "together would exceed its session draw limit. Central Pharmacy data is 7 h old."
    )
    log = store.query_pk(settings.TABLE_GATE_LOG, SESSION)
    assert len(log) == 3
    t3 = log[2]
    assert t3["cumulative_draw_qty"] == pytest.approx(18, abs=TOL)
    assert t3["cumulative_draw_limit"] == pytest.approx(12.68, abs=TOL)
    assert t3["source_p05_before"] == pytest.approx(21.14, abs=TOL)
    assert t3["source_p05_after"] == pytest.approx(3.14, abs=TOL)
    assert t3["source_report_age_h"] == 7
    assert log[1]["cumulative_draw_qty"] == pytest.approx(12, abs=TOL)
    assert 0.8 * log[1]["cumulative_draw_limit"] == pytest.approx(10.15, abs=TOL)


def test_demo_without_session_awareness_has_no_block(demo_h9):
    ts, rows, sites = _naive(demo_h9)
    out = evaluate_transfers(SESSION, ts, list(rows.values()), session_aware=False, sites=sites)
    assert [t.decision for t in out] == ["REVIEW", "REVIEW", "REVIEW"]
    assert all(t.rule_hits == ["R5_STALE_SOURCE"] for t in out)
    assert store.query_pk(settings.TABLE_GATE_LOG, SESSION) == []


def test_lantern_plan_all_approve(demo_h9):
    rows, sites = demo_h9
    ts = propose(list(rows.values()), sites, "lantern", "plan_wildfire_demo_01_lantern_h009")
    out = evaluate_transfers("sess_l", ts, list(rows.values()), sites=sites)
    assert [t.decision for t in out] == ["APPROVE"] * 3
    log = store.query_pk(settings.TABLE_GATE_LOG, "sess_l")
    assert log[-1]["cumulative_draw_limit"] == pytest.approx(23.82, abs=TOL)
    assert [r["dest_tts_p05_h_after"] for r in log] == [
        pytest.approx(58.3, abs=0.1),
        pytest.approx(42.2, abs=0.1),
        pytest.approx(71.0, abs=0.1),
    ]


def test_session_accumulates_across_plans(demo_h9):
    rows, sites = demo_h9
    inv = list(rows.values())

    def t(pid, n, qty):
        return Transfer(
            transfer_id=f"{pid}_t{n:02d}",
            plan_id=pid,
            source_site_id="S03",
            dest_site_id="S02",
            supply_id="insulin",
            qty=qty,
            priority_rank=n,
            distance_km=5.5,
        )

    p1, p2 = "plan_wildfire_demo_01_lantern_h009", "plan_wildfire_demo_01_lantern_h010"
    assert evaluate_transfers("sess_acc", [t(p1, 1, 6), t(p1, 2, 6)], inv, sites=sites)[1].decision == "APPROVE"
    # second plan in the same session: 12 earlier + 6 + 6 = 24 > 23.82 -> BLOCK on the last one
    out = evaluate_transfers("sess_acc", [t(p2, 1, 6), t(p2, 2, 6)], inv, sites=sites)
    assert out[0].decision == "APPROVE"
    assert out[1].decision == "BLOCK" and "R4_SESSION_DRAW" in out[1].rule_hits
    # re-planning plan 2 at the same hour does not count its own old rows
    again = evaluate_transfers("sess_acc", [t(p2, 1, 6), t(p2, 2, 6)], inv, sites=sites)
    assert [x.decision for x in again] == [x.decision for x in out]


def test_blocked_draws_do_not_count(demo_h9):
    rows, sites = demo_h9
    inv = list(rows.values())
    pid = "plan_wildfire_demo_01_lantern_h009"
    big = Transfer(transfer_id=f"{pid}_t01", plan_id=pid, source_site_id="S03", dest_site_id="S02",
                   supply_id="insulin", qty=25, priority_rank=1, distance_km=5.5)  # fmt: skip
    small = big.model_copy(update={"transfer_id": f"{pid}_t02", "qty": 6, "priority_rank": 2})
    out = evaluate_transfers("sess_b", [big, small], inv, sites=sites)
    assert out[0].decision == "BLOCK" and out[1].decision == "APPROVE"
