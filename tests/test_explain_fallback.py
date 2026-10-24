from explain.bedrock_client import set_client
from explain.bedrock_explain import explain_plan
from lantern_core.config import settings
from lantern_core.schemas import Counts, Plan, Transfer


class _Stub:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def converse(self, **_kwargs):
        self.calls += 1
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def _plan() -> Plan:
    pid = "plan_wildfire_demo_01_lantern_h009"
    return Plan(
        scenario_id="wildfire_demo_01",
        plan_id=pid,
        session_id="sess_x",
        planner="lantern",
        sim_hour=9,
        data_loss_pct=40,
        apply_gate=True,
        transfers=[
            Transfer(
                transfer_id=f"{pid}_t01",
                plan_id=pid,
                source_site_id="S03",
                dest_site_id="S02",
                supply_id="insulin",
                qty=6,
                priority_rank=1,
                distance_km=5.48,
                decision="APPROVE",
                rule_hits=[],
                reason_text="All five safety rules pass.",
            )
        ],
        counts=Counts(approve=1),
        created_at="2026-11-07T17:00:00Z",
    )


def test_bedrock_off_uses_templates_and_keeps_decisions():
    settings.BEDROCK_ENABLED = False
    plan = explain_plan(_plan(), sites=[{"site_id": "S03", "name": "Riverside Clinic"}, {"site_id": "S02", "name": "Shelter B"}])
    assert plan.explanation_source == "template"
    assert plan.transfers[0].decision == "APPROVE"
    assert plan.transfers[0].explanation_text
    assert "APPROVE" in plan.summary_text or "1 APPROVE" in plan.summary_text


def test_bad_json_falls_back_to_templates():
    settings.BEDROCK_ENABLED = True
    stub = _Stub("this is not json at all")
    set_client(stub)
    plan = explain_plan(_plan(), sites=[{"site_id": "S03", "name": "Riverside Clinic"}, {"site_id": "S02", "name": "Shelter B"}])
    assert stub.calls >= 1
    assert plan.explanation_source == "template"
    assert plan.transfers[0].decision == "APPROVE"


def test_stubbed_bedrock_valid_json_is_used():
    settings.BEDROCK_ENABLED = True
    pid = "plan_wildfire_demo_01_lantern_h009_t01"
    stub = _Stub(
        '{"summary_text": "Lantern sends insulin from the live clinic.",'
        f' "explanations": {{"{pid}": "APPROVE this live-clinic transfer."}}}}'
    )
    set_client(stub)
    plan = explain_plan(_plan(), sites=[{"site_id": "S03", "name": "Riverside Clinic"}, {"site_id": "S02", "name": "Shelter B"}])
    assert plan.explanation_source == "bedrock"
    assert plan.summary_text == "Lantern sends insulin from the live clinic."
    assert plan.transfers[0].explanation_text.startswith("APPROVE")
    assert plan.transfers[0].decision == "APPROVE"


def test_contradicting_decision_word_is_rejected():
    settings.BEDROCK_ENABLED = True
    pid = "plan_wildfire_demo_01_lantern_h009_t01"
    stub = _Stub(
        '{"summary_text": "ok",'
        f' "explanations": {{"{pid}": "We should BLOCK this transfer."}}}}'
    )
    set_client(stub)
    plan = explain_plan(_plan(), sites=[{"site_id": "S03", "name": "Riverside Clinic"}, {"site_id": "S02", "name": "Shelter B"}])
    assert plan.explanation_source == "template"
