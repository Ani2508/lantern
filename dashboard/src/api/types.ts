// Field names copied from contract 2.6 / 2.7 (lantern_core/schemas.py). OWNER: M5.

export type Decision = "APPROVE" | "REVIEW" | "BLOCK";
export type PlannerId = "equal_split" | "naive" | "lantern";
export type SiteType = "shelter" | "clinic" | "pharmacy" | "food_bank";
export type SupplyId = "water" | "food" | "insulin";

export interface Site {
  scenario_id: string;
  site_id: string;
  name: string;
  site_type: SiteType;
  lat: number;
  lon: number;
  people_served: number;
  created_at: string;
}

export interface InventoryState {
  scenario_id: string;
  site_supply: string;
  site_id: string;
  supply_id: SupplyId;
  sim_hour: number;
  last_reported_qty: number;
  last_report_hour: number;
  report_age_h: number;
  data_status: "live" | "stale";
  people_served: number;
  burn_rate_per_h?: number;
  est_qty_p05?: number;
  est_qty_p50?: number;
  est_qty_p95?: number;
  tts_p05_h?: number;
  tts_p50_h?: number;
  tts_p95_h?: number;
  updated_at: string;
}

export interface Transfer {
  transfer_id: string;
  plan_id: string;
  source_site_id: string;
  dest_site_id: string;
  supply_id: SupplyId;
  qty: number;
  priority_rank: number;
  distance_km: number;
  decision?: Decision;
  rule_hits?: string[];
  reason_text?: string;
  explanation_text?: string;
}

export interface ScoutVisit {
  scout_id: string;
  site_id: string;
  supply_ids: SupplyId[];
  voi_score: number;
  reason_text: string;
}

export interface Plan {
  scenario_id: string;
  plan_id: string;
  session_id: string;
  planner: PlannerId;
  sim_hour: number;
  data_loss_pct: number;
  apply_gate: boolean;
  transfers: Transfer[];
  scouts: ScoutVisit[];
  counts: { approve: number; review: number; block: number };
  summary_text: string;
  explanation_source: "bedrock" | "template";
  runtime_ms: number;
  created_at: string;
}

export interface GateLogRow {
  session_id: string;
  transfer_id: string;
  plan_id: string;
  scenario_id: string;
  planner: PlannerId;
  source_site_id: string;
  dest_site_id: string;
  supply_id: SupplyId;
  qty: number;
  decision: Decision;
  rule_hits: string[];
  reason_text: string;
  source_p05_before?: number;
  source_p05_after?: number;
  cumulative_draw_qty?: number;
  cumulative_draw_limit?: number;
  source_report_age_h?: number;
  dest_tts_p05_after_h?: number;
  created_at: string;
}

export interface ScenarioState {
  sim_hour: number;
  sites: Site[];
  inventory: InventoryState[];
}

export interface ProofRow {
  planner: PlannerId;
  data_loss_pct: number;
  seed: number;
  shortage_hours: number;
  unmet_demand_units: number;
}

export interface ProofChart {
  rows: ProofRow[];
  summary: {
    seeds?: number;
    unsafe_total?: number;
    unsafe_caught_session?: number;
    interval_coverage_90?: number | null;
    replan_seconds_p50?: number | null;
    preliminary?: boolean;
  };
}
