export type SiteType = "shelter" | "clinic" | "pharmacy" | "food_bank";
export type PlannerName = "equal_split" | "naive" | "lantern";
export type Decision = "APPROVE" | "REVIEW" | "BLOCK";
export type DataStatus = "live" | "stale";
export type ExplanationSource = "bedrock" | "template";
export type ParserSource = "bedrock" | "rules";
export type SupplyId = "water" | "food" | "insulin";
export type RuleId =
  | "R1_SOURCE_RESERVE"
  | "R2_DEST_MIN_HOURS"
  | "R3_MAX_SIZE"
  | "R4_SESSION_DRAW"
  | "R5_STALE_SOURCE";

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
  data_status: DataStatus;
  people_served: number;
  burn_rate_per_h?: number | null;
  est_qty_p05?: number | null;
  est_qty_p50?: number | null;
  est_qty_p95?: number | null;
  tts_p05_h?: number | null;
  tts_p50_h?: number | null;
  tts_p95_h?: number | null;
  updated_at?: string | null;
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
  decision?: Decision | null;
  rule_hits?: RuleId[];
  reason_text?: string | null;
  explanation_text?: string | null;
}

export interface ScoutVisit {
  scout_id: string;
  site_id: string;
  supply_ids: SupplyId[];
  voi_score: number;
  reason_text: string;
}

export interface Counts {
  approve: number;
  review: number;
  block: number;
}

export interface Plan {
  scenario_id: string;
  plan_id: string;
  session_id: string;
  planner: PlannerName;
  sim_hour: number;
  data_loss_pct: number;
  apply_gate: boolean;
  transfers: Transfer[];
  scouts: ScoutVisit[];
  counts: Counts;
  summary_text: string;
  explanation_source: ExplanationSource;
  runtime_ms: number;
  created_at: string;
}

export interface GateLogRow {
  session_id: string;
  transfer_id: string;
  plan_id: string;
  scenario_id: string;
  planner: PlannerName;
  source_site_id: string;
  dest_site_id: string;
  supply_id: SupplyId;
  qty: number;
  decision: Decision;
  rule_hits: RuleId[];
  reason_text: string;
  source_p05_before: number;
  source_p05_after: number;
  cumulative_draw_qty: number;
  cumulative_draw_limit: number;
  source_report_age_h: number;
  dest_tts_p05_h_after: number;
  created_at: string;
}

export interface FieldReportParse {
  field_report_id: string;
  scenario_id: string;
  sim_hour: number;
  source_text: string;
  site_id?: string | null;
  supply_id?: SupplyId | null;
  qty?: number | null;
  confidence: number;
  notes: string;
  parser_source: ParserSource;
  needs_confirmation: boolean;
  problems: string[];
}

export interface StateResponse {
  sim_hour: number;
  sites: Site[];
  inventory: InventoryState[];
  latest_plans: { [planner: string]: Plan };
  sessions: { [planner: string]: string };
}

export interface PublicConfig {
  banner: string;
  planner_names: { [k: string]: string };
  bedrock_enabled: boolean;
  notify_enabled: boolean;
  mode: string;
}

export interface ProofChartResponse {
  rows: Array<{
    planner: string;
    data_loss_pct: number;
    seed: number;
    shortage_hours: number;
    unmet_demand_units: number;
  }>;
  summary: Record<string, unknown>;
  sensitivity?: Array<{ stale_qty_frac: number; data_loss_pct: number; shortage_hours_mean: number }>;
}
