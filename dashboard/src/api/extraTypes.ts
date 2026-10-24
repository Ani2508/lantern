/** Types for the additive routes (single-check, events). The v1.2 contract types stay in types.ts. */
import type { Decision, RuleId, SupplyId } from "./types";

export interface SingleCheckRow {
  transfer_id: string;
  decision: Decision;
  rule_hits: RuleId[];
  reason_text: string;
}

export type ScenarioEvent =
  | { sim_hour: number; type: "hazard_start"; hazard: string }
  | { sim_hour: number; type: "site_dark"; site_ids: string[] }
  | { sim_hour: number; type: "evacuee_arrival"; site_id: string; people: number }
  | { sim_hour: number; type: "demand_spike"; site_id: string; supply_id: SupplyId; extra_qty: number; over_hours: number }
  | { sim_hour: number; type: "delivery"; site_id: string; supply_id: SupplyId; extra_qty: number };

/** /api/config/public plus the additive LLM provider fields. */
export interface PublicConfigX {
  banner: string;
  planner_names: { [k: string]: string };
  bedrock_enabled: boolean;
  notify_enabled: boolean;
  mode: string;
  llm_provider?: "bedrock" | "ollama";
  llm_model?: string;
}
