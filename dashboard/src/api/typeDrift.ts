/** Type-drift check: mock JSON must have every contract field. The build fails on rename/drop. */
import type { GateLogRow, Plan, StateResponse } from "./types";
import lantern from "../mocks/plan_lantern_h009.json";
import naive from "../mocks/plan_naive_h009.json";
import state0 from "../mocks/state_h000.json";
import state9 from "../mocks/state_h009.json";
import gateLog from "../mocks/gate_log_naive.json";

type Widen<T> = T extends string
  ? string
  : T extends number
    ? number
    : T extends boolean
      ? boolean
      : T extends Array<infer U>
        ? Array<Widen<U>>
        : T extends object
          ? { [K in keyof T]: Widen<T[K]> }
          : T;

export const _naive: Widen<Plan> = naive;
export const _lantern: Widen<Plan> = lantern;
export const _state0: Widen<StateResponse> = state0;
export const _state9: Widen<StateResponse> = state9;
export const _gateLog: Widen<GateLogRow[]> = gateLog;
