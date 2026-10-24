"""make local-demo: the whole pipeline offline on wildfire_demo_01. OWNER: M1 (wired by M3).

reset -> step to hour 9 -> naive plan (gated) -> lantern plan -> print both.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.planner import run_plan  # noqa: E402
from gate import gate as gate_module  # noqa: E402
from lantern_core.ids import session_id  # noqa: E402
from simulator.run import reset, step  # noqa: E402

SCENARIO = "wildfire_demo_01"


def show(plan) -> None:
    c = plan.counts
    print(f"\n=== {plan.planner.upper()}  {plan.plan_id}  ({plan.data_loss_pct:.0f}% of sites dark, {plan.runtime_ms} ms)")
    print(f"    {c.approve} APPROVE · {c.review} REVIEW · {c.block} BLOCK")
    for t in plan.transfers:
        d = t.decision or "-"
        print(f"    {t.transfer_id[-3:]}  {t.source_site_id} -> {t.dest_site_id}  {t.supply_id:<8}{t.qty:>7.0f}  {d:<7} {', '.join(t.rule_hits)}")
    for s in plan.scouts:
        print(f"    SCOUT {s.site_id} ({s.voi_score:.2f}): {s.reason_text}")
    print(f"    {plan.summary_text}")


def main() -> None:
    reset(SCENARIO)
    step(SCENARIO, 9)
    if getattr(gate_module, "IS_STUB", False):
        print("NOTE: gate is still M4's stub, so every transfer shows APPROVE.")
    show(run_plan(SCENARIO, 9, "naive", session_id(SCENARIO, "naive"), apply_gate=True))
    show(run_plan(SCENARIO, 9, "lantern", session_id(SCENARIO, "lantern"), apply_gate=True))


if __name__ == "__main__":
    main()
