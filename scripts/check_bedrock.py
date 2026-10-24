"""Live Bedrock check: parse both sample field reports and explain the hour-9 Lantern plan."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.demo_story import FIELD_REPORTS, mode, run_story  # noqa: E402
from explain.bedrock_explain import explain_plan  # noqa: E402
from explain.field_report import parse_field_report  # noqa: E402
from lantern_core.config import DEMO_SCENARIO_ID, settings  # noqa: E402


def main() -> None:
    if not settings.BEDROCK_ENABLED:
        print("BEDROCK_ENABLED is false (it turns LLM text on for LLM_PROVIDER). Set it to true in .env.")
        sys.exit(2)
    with mode(settings.LANTERN_MODE if settings.LANTERN_MODE != "memory" else "memory"):
        story = run_story(with_field_report=False)
        sites = story["state_before_plans"]["sites"]
        inventory = story["state_before_plans"]["inventory"]
        ok = True
        for fr in FIELD_REPORTS:
            p = parse_field_report(DEMO_SCENARIO_ID, fr["text"], inventory=inventory, sites=sites)
            print(f"parse: parser_source={p.parser_source} {p.site_id} {p.supply_id} qty={p.qty} conf={p.confidence}")
            exp = fr["expected"]
            if (p.site_id, p.supply_id, p.qty) != (exp["site_id"], exp["supply_id"], exp["qty"]):
                print("  FAIL: expected", exp)
                ok = False
            if p.parser_source != "bedrock":
                print("  FAIL: expected parser_source=bedrock")
                ok = False
        explained = explain_plan(story["plan_lantern"], sites=sites)
        print(f"explain: explanation_source={explained.explanation_source}")
        print(explained.summary_text)
        if explained.explanation_source != "bedrock":
            print("FAIL: expected explanation_source=bedrock")
            ok = False
        print(json.dumps({"ok": ok, "provider": settings.LLM_PROVIDER, "models": settings.llm_model_ids}, indent=2))
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
