import json

from explain.bedrock_client import set_client
from explain.field_report import parse_field_report, parse_rules
from lantern_core.config import settings
from simulator import run
from tests.conftest import FIXTURE_DIR

DEMO = "wildfire_demo_01"
SAMPLES = json.loads((FIXTURE_DIR / "field_reports.json").read_text(encoding="utf-8"))


class _Stub:
    def __init__(self, text: str):
        self.text = text

    def converse(self, **_kwargs):
        return {"output": {"message": {"content": [{"text": self.text}]}}}


def _sites():
    return json.loads((FIXTURE_DIR / "sites.json").read_text(encoding="utf-8"))


def test_rules_parser_handles_both_samples():
    sites = _sites()
    for sample in SAMPLES:
        got = parse_rules(sample["text"], sites)
        exp = sample["expected"]
        assert (got["site_id"], got["supply_id"], got["qty"]) == (exp["site_id"], exp["supply_id"], exp["qty"])


def test_rules_parse_through_full_path(demo_h9):
    run.reset(DEMO)
    run.step(DEMO, 9)
    p1 = parse_field_report(DEMO, SAMPLES[0]["text"])
    assert (p1.site_id, p1.supply_id, p1.qty, p1.parser_source) == ("S04", "insulin", 19, "rules")
    assert p1.needs_confirmation is False
    p2 = parse_field_report(DEMO, SAMPLES[1]["text"])
    assert (p2.site_id, p2.supply_id, p2.qty) == ("S02", "insulin", 1)
    assert p2.needs_confirmation and "Low confidence" in p2.notes


def test_stubbed_bedrock_valid_parse(demo_h9):
    settings.BEDROCK_ENABLED = True
    set_client(_Stub('{"site_id":"S04","supply_id":"insulin","qty":19,"confidence":0.92,"notes":"counted"}'))
    run.reset(DEMO)
    run.step(DEMO, 9)
    p = parse_field_report(DEMO, SAMPLES[0]["text"])
    assert p.parser_source == "bedrock"
    assert (p.site_id, p.supply_id, p.qty) == ("S04", "insulin", 19)
    assert p.confidence == 0.92


def test_out_of_range_or_low_confidence_held(demo_h9):
    run.reset(DEMO)
    run.step(DEMO, 9)
    held = parse_field_report(DEMO, "at central pharmacy maybe 200 vials of insulin")
    assert held.site_id == "S04" and held.supply_id == "insulin" and held.qty == 200
    assert held.needs_confirmation
    assert held.problems or "Held" in held.notes


def test_unknown_site_rejected(demo_h9):
    run.reset(DEMO)
    run.step(DEMO, 9)
    p = parse_field_report(DEMO, "at the airport hangar counted 19 vials of insulin")
    assert p.site_id is None
    assert p.needs_confirmation
    assert any("site" in x.lower() for x in p.problems)
