// One interface, two sources: mock (the shared fixtures, offline) and live (the API of contract 2.10).
// Switch with VITE_USE_MOCKS in the repo's .env.  OWNER: M5.
import type { GateLogRow, Plan, PlannerId, ProofChart, ScenarioState, Site } from "./types";
import { estimate } from "../lib/domain";
import proofMock from "../mocks/proof_chart.json";

import sitesFx from "../../../tests/fixtures/wildfire_demo_01/sites.json";
import naiveFx from "../../../tests/fixtures/wildfire_demo_01/plan_naive_h009.json";
import lanternFx from "../../../tests/fixtures/wildfire_demo_01/plan_lantern_h009.json";
import equalFx from "../../../tests/fixtures/wildfire_demo_01/plan_equal_split_h009.json";
import gateLogFx from "../../../tests/fixtures/wildfire_demo_01/gate_log_naive_h009.json";

export const SCENARIO = "wildfire_demo_01";

export interface DataSource {
  mode: "mock" | "live";
  maxHour: number;
  planHours: number[] | "any";
  reset(): Promise<number>;
  step(toHour: number): Promise<number>;
  state(): Promise<ScenarioState>;
  plan(planner: PlannerId): Promise<Plan>;
  gateLog(sessionId: string): Promise<GateLogRow[]>;
  proof(): Promise<ProofChart>;
}

// ---------- mock -----------------------------------------------------------
const reportFiles = import.meta.glob("../../../tests/fixtures/wildfire_demo_01/reports/*.jsonl", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

interface Report {
  scenario_id: string;
  sim_hour: number;
  site_id: string;
  supply_id: "water" | "food" | "insulin";
  qty: number;
  people_served: number;
}

const reportsByHour: Record<number, Report[]> = {};
for (const [path, text] of Object.entries(reportFiles)) {
  const hour = Number(path.match(/h(\d{3})\.jsonl$/)?.[1]);
  reportsByHour[hour] = text
    .split("\n")
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l) as Report);
}
const MOCK_MAX_HOUR = Math.max(...Object.keys(reportsByHour).map(Number));

/** Same rules as ingest/handler.py: newest report wins; silent sites age by one hour each hour. */
function mockStateAt(hour: number): ScenarioState {
  const rows = new Map<string, ScenarioState["inventory"][number]>();
  for (let h = 0; h <= hour; h++) {
    const seen = new Set<string>();
    for (const r of reportsByHour[h] ?? []) {
      const key = `${r.site_id}#${r.supply_id}`;
      seen.add(key);
      rows.set(key, {
        scenario_id: SCENARIO, site_supply: key, site_id: r.site_id, supply_id: r.supply_id, sim_hour: h,
        last_reported_qty: r.qty, last_report_hour: h, report_age_h: 0, data_status: "live",
        people_served: r.people_served, updated_at: "",
      });
    }
    for (const [key, row] of rows) {
      if (seen.has(key)) continue;
      const age = h - row.last_report_hour;
      rows.set(key, { ...row, sim_hour: h, report_age_h: age, data_status: age < 1 ? "live" : "stale" });
    }
  }
  return { sim_hour: hour, sites: sitesFx as Site[], inventory: [...rows.values()].map(estimate) };
}

function mockSource(): DataSource {
  let hour = 0;
  const plans: Record<PlannerId, Plan> = {
    naive: naiveFx as Plan,
    lantern: lanternFx as Plan,
    equal_split: equalFx as Plan,
  };
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
  return {
    mode: "mock",
    maxHour: MOCK_MAX_HOUR,
    planHours: [9],
    async reset() {
      hour = 0;
      return 0;
    },
    async step(to) {
      hour = Math.max(0, Math.min(MOCK_MAX_HOUR, to));
      return hour;
    },
    async state() {
      return mockStateAt(hour);
    },
    async plan(planner) {
      await wait(450); // feels like a real re-plan on video
      if (hour !== 9) throw new Error("Offline demo data has plans for hour 9 only. Move the timeline to 17:00.");
      return plans[planner];
    },
    async gateLog() {
      return gateLogFx as GateLogRow[];
    },
    async proof() {
      return proofMock as ProofChart;
    },
  };
}

// ---------- live -----------------------------------------------------------
function liveSource(base: string): DataSource {
  const call = async <T,>(method: string, path: string, body?: unknown): Promise<T> => {
    const res = await fetch(`${base}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || `${method} ${path} failed (${res.status})`);
    return data as T;
  };
  let hour = 0;
  return {
    mode: "live",
    maxHour: 71,
    planHours: "any",
    async reset() {
      hour = (await call<{ sim_hour: number }>("POST", `/scenarios/${SCENARIO}/reset`)).sim_hour;
      return hour;
    },
    async step(to) {
      if (to < hour) await this.reset(); // the simulator only moves forward
      if (to > hour) hour = (await call<{ sim_hour: number }>("POST", `/scenarios/${SCENARIO}/step`, { to_hour: to })).sim_hour;
      return hour;
    },
    state: () => call<ScenarioState>("GET", `/scenarios/${SCENARIO}/state`),
    plan: (planner) => call<Plan>("POST", `/scenarios/${SCENARIO}/plan`, { planner, apply_gate: true }),
    gateLog: (sid) => call<GateLogRow[]>("GET", `/sessions/${sid}/gate-log`),
    proof: () => call<ProofChart>("GET", `/eval/proof-chart`).catch(() => proofMock as ProofChart),
  };
}

const useMocks = (import.meta.env.VITE_USE_MOCKS ?? "true") !== "false";
export const api: DataSource = useMocks
  ? mockSource()
  : liveSource((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "/api");
