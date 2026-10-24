"""Closed-loop evaluation -> proof chart files (contract 2.9). OWNER: M2.
DRAFT by M3 for M2 review.

For each hazard x DATA_LOSS_LEVELS x seed, and each planner (equal_split,
naive, lantern), the SAME world is run for 72 h:
  every hour   sites report -> ingest
  every 6 h    run_plan; APPROVE and REVIEW transfers move TRUE stock
               (naive runs ungated, so all its transfers move)
Runs in memory mode with NOTIFY_ENABLED=false and BEDROCK_ENABLED=false.

    python -m eval.run_eval                 # full: 3 x 8 x 20 = 480 worlds x 3 planners
    python -m eval.run_eval --seeds 3       # quick
Writes eval/results/proof_chart.csv, summary.json, sensitivity.csv to the
store chosen by LANTERN_MODE *before* switching to memory (local or aws).
"""

from __future__ import annotations

import argparse
import io
import json
import statistics
import time

import pandas as pd

from engine import estimator
from engine.planner import run_plan
from eval.metrics import unsafe_flags
from gate.gate import evaluate_transfers
from ingest.handler import process_hour
from lantern_core import store
from lantern_core.config import settings
from lantern_core.ids import iso, report_key, scenario_id, sim_time
from lantern_core.schemas import InventoryState, Site
from simulator.world import World

HAZARDS = ["wildfire", "flood", "power_loss"]
PLANNERS = ["equal_split", "naive", "lantern"]


def _load_model_bytes() -> dict[str, bytes]:
    """Read the trained forecaster from the real store before switching to memory."""
    out = {}
    from engine import forecaster

    for key in (settings.forecaster_model_key, forecaster.metrics_key()):
        try:
            out[key] = store.get_object(key)
        except KeyError:
            pass
    return out


def run_world(sid: str, planner: str, model: dict[str, bytes], unsafe: dict) -> tuple[World, list[float]]:
    from engine import forecaster

    store.reset_memory()
    for k, v in model.items():
        store.put_object(k, v)
    forecaster.reload_model()
    w = World(sid)
    base = f"raw/scenarios/{sid}"
    sites = w.site_rows(iso(sim_time(settings.sim_start_ts, 0)))
    store.put_json(f"{base}/sites.json", sites)
    store.put_json(f"{base}/events.json", w.events())
    store.batch_put(settings.table_sites, [Site(**s).to_item() for s in sites])
    weather_lines = ""
    runtimes: list[float] = []
    for h in range(w.hours):
        weather_lines += json.dumps(w.weather()) + "\n"
        store.put_object(f"{base}/weather.jsonl", weather_lines)
        store.put_object(report_key(sid, h), "".join(json.dumps(r) + "\n" for r in w.reports()))
        process_hour(sid, h, reset=(h == 0))
        if h > 0 and h % settings.replan_every_h == 0:
            # one gate session per re-plan: a session is one round of decisions
            plan = run_plan(sid, h, planner, f"sess_{sid}_{planner}_h{h:03d}", apply_gate=(planner != "naive"))
            runtimes.append(plan.runtime_ms / 1000)
            if planner == "naive" and plan.transfers:
                flags = unsafe_flags(w, plan.transfers)
                inv = [InventoryState(**r) for r in store.query_pk(settings.table_inventory, sid)]
                inv = estimator.estimate(inv)
                sess = evaluate_transfers(f"chk_{sid}_{h}", plan.transfers, inv, session_aware=True)
                single = evaluate_transfers(f"chk1_{sid}_{h}", plan.transfers, inv, session_aware=False)
                for f, a, b in zip(flags, sess, single, strict=True):
                    if f:
                        unsafe["total"] += 1
                        unsafe["session"] += a.decision in ("BLOCK", "REVIEW")
                        unsafe["single"] += b.decision in ("BLOCK", "REVIEW")
                        unsafe["blocked_session"] += a.decision == "BLOCK"
                        unsafe["blocked_single"] += b.decision == "BLOCK"
            for t in plan.transfers:
                if t.decision in (None, "APPROVE", "REVIEW"):
                    w.transfer(t.source_site_id, t.dest_site_id, t.supply_id, t.qty)
        w.advance()
    return w, runtimes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=settings.eval_seeds)
    ap.add_argument("--sens-seeds", type=int, default=5)
    ap.add_argument("--no-sensitivity", action="store_true")
    a = ap.parse_args()

    model = _load_model_bytes()
    out_mode = settings.lantern_mode
    settings.lantern_mode = "memory"
    settings.notify_enabled = False
    settings.bedrock_enabled = False

    t0 = time.time()
    rows, runtimes = [], []
    unsafe = {"total": 0, "session": 0, "single": 0, "blocked_session": 0, "blocked_single": 0}
    for hazard in HAZARDS:
        for loss in settings.data_loss_levels:
            for seed in range(a.seeds):
                sid = scenario_id("eval", hazard, seed, loss)
                for planner in PLANNERS:
                    w, rt = run_world(sid, planner, model, unsafe)
                    if planner == "lantern":
                        runtimes.extend(rt)
                    rows.append({"planner": planner, "data_loss_pct": loss, "seed": seed, "hazard": hazard,
                                 "shortage_hours": w.shortage_hours, "unmet_demand_units": round(w.unmet_total, 2)})
        print(f"  {hazard} done ({time.time() - t0:.0f}s)")

    df = pd.DataFrame(rows)
    sens = []
    if not a.no_sensitivity:
        base_frac = settings.stale_qty_frac
        for frac in (0.02, 0.04, 0.06):
            settings.stale_qty_frac = frac
            for loss in settings.data_loss_levels:
                vals = []
                for hazard in HAZARDS:
                    for seed in range(min(a.sens_seeds, a.seeds)):
                        w, _ = run_world(scenario_id("eval", hazard, seed, loss), "lantern", model, {"total": 0, "session": 0, "single": 0, "blocked_session": 0, "blocked_single": 0})
                        vals.append(w.shortage_hours)
                sens.append({"stale_qty_frac": frac, "data_loss_pct": loss, "shortage_hours_mean": statistics.mean(vals)})
        settings.stale_qty_frac = base_frac

    coverage = None
    if model:
        from engine import forecaster

        meta = json.loads(model.get(forecaster.metrics_key(), b"{}") or b"{}")
        coverage = meta.get("interval_coverage_90")

    means = df.groupby(["planner", "data_loss_pct"])["shortage_hours"].mean()
    summary = {
        "generated_at": iso(),
        "seeds": a.seeds,
        "shortage_hours_mean": {p: {str(k): round(float(v), 2) for k, v in means[p].items()} for p in PLANNERS},
        "unsafe_caught_session": unsafe["session"],
        "unsafe_caught_single": unsafe["single"],
        "unsafe_total": unsafe["total"],
        # extra (not in contract 2.9 yet): BLOCK only, since R5 sends every stale-source transfer to REVIEW
        "unsafe_blocked_session": unsafe["blocked_session"],
        "unsafe_blocked_single": unsafe["blocked_single"],
        "interval_coverage_90": coverage,
        "replan_seconds_p50": round(statistics.median(runtimes), 3) if runtimes else None,
        "note": "simulation only; replan time measured locally (use CloudWatch for the Lambda figure)",
    }

    settings.lantern_mode = out_mode
    buf = io.StringIO()
    df[["planner", "data_loss_pct", "seed", "shortage_hours", "unmet_demand_units"]].to_csv(buf, index=False)
    store.put_object("eval/results/proof_chart.csv", buf.getvalue())
    store.put_json("eval/results/summary.json", summary)
    if sens:
        buf = io.StringIO()
        pd.DataFrame(sens).to_csv(buf, index=False)
        store.put_object("eval/results/sensitivity.csv", buf.getvalue())
    print(json.dumps({k: v for k, v in summary.items() if k != "shortage_hours_mean"}, indent=1))
    print(means.unstack(0).round(1).to_string())
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
