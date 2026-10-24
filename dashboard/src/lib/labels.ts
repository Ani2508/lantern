/** Plain-English labels and icons for every raw code the API returns. */
import {
  Droplet,
  Pill,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  Stethoscope,
  Syringe,
  Tent,
  Warehouse,
  Wheat,
  type LucideIcon,
} from "lucide-react";
import type { Decision, InventoryState, RuleId, Site, SiteType, SupplyId } from "../api/types";

export const SUPPLY: Record<SupplyId, { label: string; unit: string; Icon: LucideIcon }> = {
  water: { label: "Water", unit: "gal", Icon: Droplet },
  food: { label: "Food", unit: "meals", Icon: Wheat },
  insulin: { label: "Insulin", unit: "vials", Icon: Syringe },
};
export const SUPPLY_ORDER: SupplyId[] = ["insulin", "water", "food"];

export const SITE_TYPE: Record<SiteType, { label: string; Icon: LucideIcon }> = {
  shelter: { label: "Shelter", Icon: Tent },
  clinic: { label: "Clinic", Icon: Stethoscope },
  pharmacy: { label: "Pharmacy", Icon: Pill },
  food_bank: { label: "Food bank", Icon: Warehouse },
};

export const RULES: Record<RuleId, { short: string; long: string }> = {
  R1_SOURCE_RESERVE: { short: "Source reserve", long: "Source would fall below its worst-case reserve" },
  R2_DEST_MIN_HOURS: { short: "Destination still short", long: "Destination still runs out too soon" },
  R3_MAX_SIZE: { short: "Too large", long: "One transfer is too big a share of the source" },
  R4_SESSION_DRAW: { short: "Running total", long: "Transfers from this source add up past its session limit" },
  R5_STALE_SOURCE: { short: "Stale data", long: "The source's count is hours old" },
};

export const DECISION: Record<Decision, { label: string; Icon: LucideIcon }> = {
  APPROVE: { label: "Approved", Icon: ShieldCheck },
  REVIEW: { label: "Needs review", Icon: ShieldAlert },
  BLOCK: { label: "Blocked", Icon: ShieldX },
};

export function fmtQty(q: number | null | undefined, supply?: SupplyId): string {
  if (q == null || Number.isNaN(q)) return "—";
  if (supply === "insulin" || Math.abs(q) < 10) return (Math.round(q * 10) / 10).toLocaleString();
  return Math.round(q).toLocaleString();
}

export function qtyWithUnit(q: number | null | undefined, supply: SupplyId): string {
  return `${fmtQty(q, supply)} ${SUPPLY[supply].unit}`;
}

/** "21–58" when the estimate is uncertain, "19" when it is a fresh count. */
export function rangeText(r: InventoryState): string {
  const lo = r.est_qty_p05 ?? r.last_reported_qty;
  const hi = r.est_qty_p95 ?? r.last_reported_qty;
  if (Math.abs(hi - lo) < 0.05) return fmtQty(r.est_qty_p50 ?? lo, r.supply_id);
  return `${fmtQty(lo, r.supply_id)}–${fmtQty(hi, r.supply_id)}`;
}

export function voiLabel(score: number): string {
  return score >= 2 ? "high" : score >= 1 ? "medium" : "low";
}

export type SiteStatus = "live" | "stale" | "mixed";

export function siteStatus(rows: InventoryState[]): SiteStatus {
  if (!rows.length || rows.every((r) => r.data_status === "live")) return "live";
  if (rows.every((r) => r.data_status === "stale")) return "stale";
  return "mixed";
}

export function siteAge(rows: InventoryState[]): number {
  return Math.max(0, ...rows.map((r) => r.report_age_h));
}

/** 0..1: how wide the critical supply's p05..p95 band is relative to its middle estimate. */
export function siteSpread(rows: InventoryState[]): number {
  const critical = rows.filter((r) => r.supply_id === "insulin");
  let worst = 0;
  for (const r of critical.length ? critical : rows) {
    const lo = r.est_qty_p05 ?? 0;
    const hi = r.est_qty_p95 ?? 0;
    const mid = Math.max(r.est_qty_p50 ?? 0, 1);
    worst = Math.max(worst, (hi - lo) / mid);
  }
  return Math.min(1, worst);
}

export function namer(sites: Site[]) {
  const m = Object.fromEntries(sites.map((s) => [s.site_id, s.name]));
  return (id: string | null | undefined) => (id ? m[id] || id : "—");
}
