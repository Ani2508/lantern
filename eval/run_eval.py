"""Closed-loop evaluation: every planner × data-loss level × seed (contract 2.9).

Runs in memory mode with Bedrock and notify off. --seeds 5 for development;
the default is EVAL_SEEDS (20) = 480 worlds.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import statistics
import time

from engine.estimator import estimate
from engine.planner import run_plan
from eval import metrics
from gate.gate import evaluate_transfers
from lantern_core import ids, store
from lantern_core.config import settings
from lantern_core.schemas import Transfer
from simulator import run as sim
from simulator.generator import eval_ids, truth_key

log = logging.getLogger(__name__)
PLANNERS = ("equal_split", "naive", "lantern")
SENSITIVITY_FRACS = (0.02, 0.04, 0.06)
PROOF_COLUMNS = ["planner", "data_loss_pct", "seed", "shortage_hours", "unmet_demand_units"]
SENS_COLUMNS = ["stale_qty_frac", "data_loss_pct", "shortage_hours_mean"]


def _bare(transfers: list[Transfer]) -> list[Transfer]:
    keys = ("transfer_id", "plan_id", "source_site_id", "dest_site_id", "supply_id", "qty", "priority_rank", "distance_km")
    return [Transfer.model_validate({k: getattr(t, k) for k in keys}) for t in transfers]


def _truth_at(scenario_id: str, hour: int) -> dict[tuple[str, str], dict]:
    rows = store.get_jsonl(truth_key(scenario_id))
    return {(t["site_id"], t["supply_id"]): t for t in rows if t["sim_hour"] == hour}


def _run_world(scenario_id: str, planner: str, stale_qty_frac: float | None = None) -> dict:
    old_frac = settings.STALE_QTY_FRAC
    if stale_qty_frac is not None:
        settings.STALE_QTY_FRAC = stale_qty_frac
    try:
        info = ids.parse_scenario_id(scenario_id)
        sim.reset(scenario_id)
        session = ids.session_id(scenario_id, planner)
        gate_session = ids.session_id(scenario_id, "naive") if planner == "naive" else session
        runtimes: list[float] = []
        coverage_hits = coverage_n = 0
        unsafe_total = unsafe_session = unsafe_single = 0

        for h in range(0, 72):
            if h > 0:
                sim.step(scenario_id, h)
            if h % settings.REPLAN_EVERY_H != 0:
                continue
            apply_gate = planner != "naive"
            t0 = time.perf_counter()
            plan = run_plan(scenario_id, h, planner, session, apply_gate=apply_gate)
            runtimes.append(time.perf_counter() - t0)

            inventory = estimate(store.query_pk(settings.TABLE_INVENTORY, scenario_id))
            truth = _truth_at(scenario_id, h)
            by_ss = {r["site_supply"]: r for r in inventory}
            for r in inventory:
                t = truth.get((r["site_id"], r["supply_id"]))
                if t is None or r.get("est_qty_p05") is None:
                    continue
                coverage_n += 1
                if metrics.interval_hit(t["qty"], r["est_qty_p05"], r["est_qty_p95"]):
                    coverage_hits += 1

            if planner == "naive" and plan.transfers:
                checked_s = evaluate_transfers(gate_session, _bare(plan.transfers), inventory, session_aware=True, write_log=True)
                checked_1 = evaluate_transfers(gate_session, _bare(plan.transfers), inventory, session_aware=False, write_log=False)
                for t, cs, c1 in zip(plan.transfers, checked_s, checked_1, strict=True):
                    src = truth.get((t.source_site_id, t.supply_id), {})
                    row = by_ss.get(ids.site_supply(t.source_site_id, t.supply_id), {})
                    if metrics.is_unsafe(float(src.get("qty", 0)), t.qty, t.supply_id, float(row.get("people_served", 0))):
                        unsafe_total += 1
                        if cs.decision in ("BLOCK", "REVIEW"):
                            unsafe_session += 1
                        if c1.decision in ("BLOCK", "REVIEW"):
                            unsafe_single += 1

            executed = [t for t in plan.transfers if (t.decision in ("APPROVE", "REVIEW") if apply_gate else True)]
            if executed:
                sim.apply_transfers(scenario_id, executed)

        if sim.current_hour(scenario_id) < 71:
            sim.step(scenario_id, 71)
        truth_rows = [t for t in store.get_jsonl(truth_key(scenario_id)) if t["sim_hour"] > 0]
        return {
            "planner": planner,
            "data_loss_pct": int(info["data_loss_pct"] or 0),
            "seed": int(info["seed"] or 0),
            "hazard": info["hazard"],
            "shortage_hours": metrics.shortage_hours(truth_rows),
            "unmet_demand_units": metrics.unmet_demand_units(truth_rows),
            "unsafe_total": unsafe_total,
            "unsafe_caught_session": unsafe_session,
            "unsafe_caught_single": unsafe_single,
            "coverage_hits": coverage_hits,
            "coverage_n": coverage_n,
            "runtimes": runtimes,
            "stale_qty_frac": settings.STALE_QTY_FRAC,
        }
    finally:
        settings.STALE_QTY_FRAC = old_frac


def run_eval(n_seeds: int | None = None, planners: tuple[str, ...] = PLANNERS) -> dict:
    settings.LANTERN_MODE = "memory"
    settings.BEDROCK_ENABLED = False
    settings.NOTIFY_ENABLED = False
    settings.FORECASTER_MODE = "heuristic"
    store.reset_memory()
    n_seeds = n_seeds if n_seeds is not None else settings.EVAL_SEEDS
    worlds = eval_ids(n_seeds)
    rows = []
    t0 = time.perf_counter()
    for i, sid in enumerate(worlds, 1):
        for planner in planners:
            store.reset_memory()
            rec = _run_world(sid, planner)
            rows.append(rec)
        if i % 10 == 0 or i == len(worlds):
            log.info("eval %s/%s worlds (%.0fs)", i, len(worlds), time.perf_counter() - t0)

    proof = [{k: r[k] for k in PROOF_COLUMNS} for r in rows]
    _write_csv("eval/results/proof_chart.csv", PROOF_COLUMNS, proof)

    by_pl: dict[str, dict[int, list[float]]] = {}
    for r in rows:
        by_pl.setdefault(r["planner"], {}).setdefault(r["data_loss_pct"], []).append(r["shortage_hours"])
    shortage_mean = {
        planner: {str(lv): round(statistics.fmean(vs), 3) for lv, vs in levels.items()} for planner, levels in by_pl.items()
    }
    unsafe_total = sum(r["unsafe_total"] for r in rows)
    cov_n = sum(r["coverage_n"] for r in rows)
    runtimes = [t for r in rows for t in r["runtimes"]]
    summary = {
        "shortage_hours_mean": shortage_mean,
        "unsafe_caught_session": sum(r["unsafe_caught_session"] for r in rows),
        "unsafe_caught_single": sum(r["unsafe_caught_single"] for r in rows),
        "unsafe_total": unsafe_total,
        "interval_coverage_90": round(sum(r["coverage_hits"] for r in rows) / cov_n, 4) if cov_n else None,
        "replan_seconds_p50": round(metrics.percentile(runtimes, 0.5), 4),
        "n_seeds": n_seeds,
        "n_worlds": len(worlds),
        "elapsed_s": round(time.perf_counter() - t0, 2),
    }
    _persist("eval/results/summary.json", json.dumps(summary, indent=1), "application/json")

    sens_rows = []
    for frac in SENSITIVITY_FRACS:
        by_level: dict[int, list[float]] = {}
        if abs(frac - 0.04) < 1e-9:
            for r in rows:
                if r["planner"] == "lantern":
                    by_level.setdefault(r["data_loss_pct"], []).append(r["shortage_hours"])
        else:
            for sid in worlds:
                store.reset_memory()
                rec = _run_world(sid, "lantern", stale_qty_frac=frac)
                by_level.setdefault(rec["data_loss_pct"], []).append(rec["shortage_hours"])
        for lv, vs in sorted(by_level.items()):
            sens_rows.append({"stale_qty_frac": frac, "data_loss_pct": lv, "shortage_hours_mean": round(statistics.fmean(vs), 3)})
    _write_csv("eval/results/sensitivity.csv", SENS_COLUMNS, sens_rows)
    return summary


def _persist(key: str, body: str, content_type: str) -> None:
    store.put_object(key, body, content_type=content_type)
    # memory-mode eval still leaves the files where the local API and dashboard look
    dest = settings.local_store_path / "s3" / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")


def _write_csv(key: str, columns: list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columns, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: r[c] for c in columns})
    _persist(key, buf.getvalue(), "text/csv")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=None, help="eval seeds (default EVAL_SEEDS=20; 5 for development)")
    args = ap.parse_args()
    summary = run_eval(args.seeds)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
