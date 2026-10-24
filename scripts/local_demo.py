"""Terminal version of the demo story: simulate, ingest, plan, gate, explain (LANTERN_MODE=local)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.demo_story import run_story  # noqa: E402
from lantern_core.config import BANNER, PLANNER_NAMES, settings  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _q(x: float) -> str:
    return f"{x:g}"


def print_plan(plan, names) -> None:
    print(f"\n== {PLANNER_NAMES[plan.planner]}  ({plan.plan_id}, gate={'on' if plan.apply_gate else 'off'}, "
          f"data loss {plan.data_loss_pct:g}%, {plan.runtime_ms:.0f} ms)")
    for t in plan.transfers:
        hits = ", ".join(t.rule_hits) or "-"
        print(f"  t{t.priority_rank:02d}  {t.source_site_id} -> {t.dest_site_id}  {t.supply_id:<7} {_q(t.qty):>6}  "
              f"{t.decision or 'UNCHECKED':<8} [{hits}]")
        if t.reason_text:
            print(f"        {t.reason_text}")
    if not plan.transfers:
        print("  (no transfers)")
    for s in plan.scouts:
        print(f"  SCOUT {s.site_id} ({names.get(s.site_id)}) {', '.join(s.supply_ids)}  voi={s.voi_score:g}")
        print(f"        {s.reason_text}")
    print(f"  counts: APPROVE {plan.counts.approve}  REVIEW {plan.counts.review}  BLOCK {plan.counts.block}")
    print(f"  explanation_source={plan.explanation_source}")
    print(f"  summary: {plan.summary_text}")


def main() -> None:
    print(BANNER)
    print(f"mode={settings.LANTERN_MODE} bedrock={settings.BEDROCK_ENABLED} notify={settings.NOTIFY_ENABLED}")
    story = run_story()
    state = story["state_before_plans"]
    names = {s["site_id"]: s["name"] for s in state["sites"]}

    print(f"\n== Hour {state['sim_hour']} inventory (insulin)")
    for r in sorted(state["inventory"], key=lambda r: r["site_id"]):
        if r["supply_id"] != "insulin":
            continue
        print(f"  {r['site_id']} {names[r['site_id']]:<18} {r['data_status']:<5} age {r['report_age_h']:>2g}h  "
              f"last {r['last_reported_qty']:>7.2f}  p05 {r['est_qty_p05']:>6.2f}  p50 {r['est_qty_p50']:>6.2f}  "
              f"p95 {r['est_qty_p95']:>6.2f}  tts_p05 {r['tts_p05_h']:>5.1f}h")

    naive = story["plan_naive"]
    print_plan(naive, names)
    single = story["single_transfer_check"]
    print("\n== Same naive transfers with session_aware=False (single-transfer gate)")
    for t in single:
        print(f"  {t['transfer_id'][-3:]}  {t['decision']:<8} [{', '.join(t['rule_hits'])}]")
    blocks = sum(t["decision"] == "BLOCK" for t in single)
    print(f"  -> {blocks} BLOCK without session awareness vs {naive.counts.block} BLOCK with it")

    print_plan(story["plan_lantern"], names)

    print("\n== Step 5b: field reports (Bedrock on)" if settings.BEDROCK_ENABLED else "\n== Step 5b: field reports (Bedrock off, rules parser)")
    for p in story["field_report_parses"]:
        print(f"  \"{p.source_text}\"")
        print(f"     -> {p.site_id} {p.supply_id} qty={p.qty} confidence={p.confidence} parser_source={p.parser_source} "
              f"needs_confirmation={p.needs_confirmation}")
        if p.notes:
            print(f"        notes: {p.notes}")
        if p.problems:
            print(f"        problems: {'; '.join(p.problems)}")
    row = story["confirm"]["inventory_row"]
    print(f"  confirmed report 1: {row['site_supply']} now {row['data_status']} age {row['report_age_h']}h, "
          f"p05=p50=p95={row['est_qty_p50']}; new lantern session {story['confirm']['session_id']}")
    print_plan(story["plan_lantern_after_report"], names)


if __name__ == "__main__":
    main()
