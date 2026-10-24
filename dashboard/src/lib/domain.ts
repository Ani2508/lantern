// Domain constants and the estimator, ported from lantern_core + engine/estimator.py
// (contract 2.5 / 2.8, v1.2). Used only by mock mode; live mode gets estimates from the API.
import type { InventoryState, PlannerId, SiteType, SupplyId } from "../api/types";

export const SUPPLIES: Record<SupplyId, { unit: string; units: string; perPersonPerDay: number; critical: boolean }> = {
  water: { unit: "gallon", units: "gallons", perPersonPerDay: 1.0, critical: false },
  food: { unit: "meal", units: "meals", perPersonPerDay: 3.0, critical: false },
  insulin: { unit: "vial", units: "vials", perPersonPerDay: 0.01, critical: true },
};

export const SITE_SUPPLIES: Record<SiteType, SupplyId[]> = {
  shelter: ["water", "food", "insulin"],
  clinic: ["water", "food", "insulin"],
  pharmacy: ["insulin"],
  food_bank: ["water", "food"],
};

export const PLANNER_NAMES: Record<PlannerId, string> = {
  equal_split: "Equal split",
  naive: "Naive AI (trusts old data)",
  lantern: "Lantern",
};

export const BANNER = "SIMULATED DATA · synthetic scenario for demonstration only";
export const SIM_START = Date.parse("2026-11-07T08:00:00Z");

const HORIZON = 72;
const STALE_SIGMA_FRAC = 0.35;
const STALE_QTY_FRAC = 0.04;
const Z_90 = 1.645;

const tts = (stock: number, burn: number) => (burn <= 0 ? HORIZON : Math.min(HORIZON, Math.max(0, stock / burn)));

export function estimate(row: InventoryState): InventoryState {
  const burn = (row.people_served * SUPPLIES[row.supply_id].perPersonPerDay) / 24;
  const age = row.report_age_h;
  const last = row.last_reported_qty;
  const p50 = Math.max(0, last - burn * age);
  const sigma = Math.max(STALE_SIGMA_FRAC * burn * age, STALE_QTY_FRAC * last * age);
  const p05 = Math.max(0, p50 - Z_90 * sigma);
  const p95 = p50 + Z_90 * sigma;
  return {
    ...row,
    burn_rate_per_h: burn,
    est_qty_p05: p05,
    est_qty_p50: p50,
    est_qty_p95: p95,
    tts_p05_h: tts(p05, burn),
    tts_p50_h: tts(p50, burn),
    tts_p95_h: tts(p95, burn),
  };
}

export function fmtQty(q: number | undefined): string {
  if (q === undefined) return "–";
  if (q >= 100) return Math.round(q).toLocaleString("en-US");
  if (q >= 10) return q.toFixed(0);
  return q.toFixed(1).replace(/\.0$/, "");
}

export function clockLabel(hour: number): string {
  const d = new Date(SIM_START + hour * 3600_000);
  const hh = d.getUTCHours().toString().padStart(2, "0");
  return `${hh}:00`;
}

/** 0 = certain, 1 = we have no idea. Width of the 90% range relative to the middle. */
export function uncertainty(row: InventoryState): number {
  const p05 = row.est_qty_p05 ?? row.last_reported_qty;
  const p50 = row.est_qty_p50 ?? row.last_reported_qty;
  const p95 = row.est_qty_p95 ?? row.last_reported_qty;
  return Math.min(1, (p95 - p05) / Math.max(p50, 1));
}

export function unitFor(supply: SupplyId, qty: number): string {
  return Math.abs(qty - 1) < 1e-9 ? SUPPLIES[supply].unit : SUPPLIES[supply].units;
}
