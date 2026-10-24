import type {
  FieldReportParse,
  GateLogRow,
  Plan,
  ProofChartResponse,
  PublicConfig,
  StateResponse,
} from "./types";
import type { ScenarioEvent, SingleCheckRow } from "./extraTypes";

const USE_MOCKS = String(import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";
const BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const DEMO = "wildfire_demo_01";

async function live<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!resp.ok) {
    let message = resp.statusText;
    try {
      const body = (await resp.json()) as { message?: string };
      if (body.message) message = body.message;
    } catch {
      /* keep statusText */
    }
    throw new Error(message);
  }
  return (await resp.json()) as T;
}

type Mocks = {
  state0: StateResponse;
  state9: StateResponse;
  stateAfter: StateResponse;
  naive: Plan;
  lantern: Plan;
  lanternAfter: Plan;
  parse: FieldReportParse;
  gateLog: GateLogRow[];
  chart: ProofChartResponse;
  config: PublicConfig;
  hours: StateResponse[];
  singleCheck: SingleCheckRow[];
  events: ScenarioEvent[];
};

let mocks: Mocks | null = null;
let mockHour = 0;
let mockPlans: StateResponse["latest_plans"] = {};
let mockConfirmed = false;

async function loadMocks(): Promise<Mocks> {
  if (mocks) return mocks;
  const [
    state0,
    state9,
    stateAfter,
    naive,
    lantern,
    lanternAfter,
    gateLog,
    chart,
    hours,
    singleCheck,
    events,
  ] = await Promise.all([
    import("../mocks/state_h000.json"),
    import("../mocks/state_h009.json"),
    import("../mocks/state_after_report.json"),
    import("../mocks/plan_naive_h009.json"),
    import("../mocks/plan_lantern_h009.json"),
    import("../mocks/plan_lantern_after_report.json"),
    import("../mocks/gate_log_naive.json"),
    import("../mocks/proof_chart.json"),
    import("../mocks/state_hours.json"),
    import("../mocks/single_check_naive.json"),
    import("../mocks/events.json"),
  ]);
  mocks = {
    state0: state0.default as StateResponse,
    state9: state9.default as StateResponse,
    stateAfter: stateAfter.default as StateResponse,
    naive: naive.default as Plan,
    lantern: lantern.default as Plan,
    lanternAfter: lanternAfter.default as Plan,
    parse: {
      field_report_id: "fr_wildfire_demo_01_h009_01",
      scenario_id: DEMO,
      sim_hour: 9,
      source_text: "at central pharmacy now, counted 19 vials of insulin, fridge ok, line out the door",
      site_id: "S04",
      supply_id: "insulin",
      qty: 19,
      confidence: 0.75,
      notes: "Rules parser: S04, insulin, 19.",
      parser_source: "rules",
      needs_confirmation: false,
      problems: [],
    },
    gateLog: gateLog.default as GateLogRow[],
    chart: chart.default as ProofChartResponse,
    hours: hours.default as unknown as StateResponse[],
    singleCheck: singleCheck.default as SingleCheckRow[],
    events: events.default as ScenarioEvent[],
    config: {
      banner: "SIMULATED DATA · synthetic scenario for demonstration only",
      planner_names: {
        equal_split: "Equal split",
        naive: "Naive AI (trusts old data)",
        lantern: "Lantern",
      },
      bedrock_enabled: false,
      notify_enabled: false,
      mode: "mock",
    },
  };
  return mocks;
}

export const usingMocks = USE_MOCKS;

export async function getConfig(): Promise<PublicConfig> {
  if (USE_MOCKS) return (await loadMocks()).config;
  return live("/config/public");
}

export async function listScenarios(): Promise<string[]> {
  if (USE_MOCKS) return [DEMO];
  return live("/scenarios");
}

export async function reset(id: string): Promise<{ sim_hour: number }> {
  if (USE_MOCKS) {
    mockHour = 0;
    mockPlans = {};
    mockConfirmed = false;
    return { sim_hour: 0 };
  }
  return live(`/scenarios/${id}/reset`, { method: "POST" });
}

export async function step(id: string, toHour: number): Promise<{ sim_hour: number }> {
  if (USE_MOCKS) {
    mockHour = toHour;
    return { sim_hour: toHour };
  }
  return live(`/scenarios/${id}/step`, { method: "POST", body: JSON.stringify({ to_hour: toHour }) });
}

export async function getState(id: string): Promise<StateResponse> {
  if (USE_MOCKS) {
    const m = await loadMocks();
    const base = mockConfirmed ? m.stateAfter : (m.hours[mockHour] ?? (mockHour >= 9 ? m.state9 : m.state0));
    return { ...base, latest_plans: mockPlans, sim_hour: mockHour };
  }
  return live(`/scenarios/${id}/state`);
}

export async function makePlan(id: string, planner: string, applyGate = true): Promise<Plan> {
  if (USE_MOCKS) {
    const m = await loadMocks();
    const plan = planner === "naive" ? m.naive : mockConfirmed ? m.lanternAfter : m.lantern;
    mockPlans = { ...mockPlans, [planner]: plan };
    return plan;
  }
  return live(`/scenarios/${id}/plan`, { method: "POST", body: JSON.stringify({ planner, apply_gate: applyGate }) });
}

export async function getPlan(planId: string): Promise<Plan> {
  if (USE_MOCKS) {
    const m = await loadMocks();
    return planId.includes("naive") ? m.naive : m.lantern;
  }
  return live(`/plans/${planId}`);
}

export async function getGateLog(sessionId: string): Promise<GateLogRow[]> {
  if (USE_MOCKS) return (await loadMocks()).gateLog;
  return live(`/sessions/${sessionId}/gate-log`);
}

export async function parseFieldReport(id: string, text: string): Promise<FieldReportParse> {
  if (USE_MOCKS) {
    const m = await loadMocks();
    return { ...m.parse, source_text: text };
  }
  return live(`/scenarios/${id}/field-report`, { method: "POST", body: JSON.stringify({ text }) });
}

export async function confirmFieldReport(
  id: string,
  parse: Pick<FieldReportParse, "field_report_id" | "site_id" | "supply_id" | "qty">,
): Promise<{ sim_hour: number; inventory_row: unknown }> {
  if (USE_MOCKS) {
    const m = await loadMocks();
    mockConfirmed = true;
    mockPlans = { ...mockPlans, lantern: m.lanternAfter };
    return { sim_hour: 9, inventory_row: m.stateAfter.inventory.find((r) => r.site_supply === "S04#insulin") };
  }
  // ConfirmBody forbids extra fields, so send exactly the four the contract names.
  const { field_report_id, site_id, supply_id, qty } = parse;
  return live(`/scenarios/${id}/field-report/confirm`, {
    method: "POST",
    body: JSON.stringify({ field_report_id, site_id, supply_id, qty }),
  });
}

export async function getProofChart(): Promise<ProofChartResponse> {
  if (USE_MOCKS) return (await loadMocks()).chart;
  return live("/eval/proof-chart");
}

export async function getStateAfterReport(): Promise<StateResponse | null> {
  if (USE_MOCKS) {
    const m = await loadMocks();
    return { ...m.stateAfter, latest_plans: mockPlans };
  }
  return null;
}

export async function getSingleCheck(planId: string): Promise<SingleCheckRow[]> {
  if (USE_MOCKS) return (await loadMocks()).singleCheck;
  return live(`/plans/${planId}/single-check`);
}

export async function getEvents(id: string): Promise<ScenarioEvent[]> {
  if (USE_MOCKS) return (await loadMocks()).events;
  return live(`/scenarios/${id}/events`);
}
