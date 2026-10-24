/** Demo orchestration: one state object, one async action per story beat, replayable from any point. */
import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../api/client";
import type { PublicConfigX, ScenarioEvent, SingleCheckRow } from "../api/extraTypes";
import type { FieldReportParse, GateLogRow, Plan, ProofChartResponse, StateResponse } from "../api/types";
import { sleep } from "../lib/motion";
import { BEATS, SAMPLE_REPORT, type BeatId } from "../story/beats";

export const DEMO = "wildfire_demo_01";
const TICK_MS = 520;

export type ToastKind = "fire" | "dark" | "people" | "live";
export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

export interface Demo {
  beat: number;
  cfg: PublicConfigX | null;
  state: StateResponse | null;
  events: ScenarioEvent[];
  naive: Plan | null;
  naiveLog: GateLogRow[];
  single: SingleCheckRow[];
  lantern: Plan | null;
  lanternBefore: Plan | null;
  parse: FieldReportParse | null;
  confirmed: boolean;
  chart: ProofChartResponse | null;
  busy: boolean;
  offline: boolean;
  toasts: Toast[];
  /** Sites that just came back online (for the re-ignite animation). */
  reignited: string[];
  /** Hour each site lost its signal (for the one-shot "signal lost" flicker). */
  lostAt: Record<string, number>;
}

const CLEAR: Partial<Demo> = {
  naive: null,
  naiveLog: [],
  single: [],
  lantern: null,
  lanternBefore: null,
  parse: null,
  confirmed: false,
  reignited: [],
  lostAt: {},
};

const EMPTY: Demo = {
  beat: 0,
  cfg: null,
  state: null,
  events: [],
  naive: null,
  naiveLog: [],
  single: [],
  lantern: null,
  lanternBefore: null,
  parse: null,
  confirmed: false,
  chart: null,
  busy: false,
  offline: false,
  toasts: [],
  reignited: [],
  lostAt: {},
};

let toastSeq = 0;

export function useDemo() {
  const [d, setD] = useState<Demo>(EMPTY);
  const ref = useRef(d);
  ref.current = d;
  const runId = useRef(0);

  const patch = useCallback((p: Partial<Demo> | ((cur: Demo) => Partial<Demo>)) => {
    setD((cur) => {
      const next = { ...cur, ...(typeof p === "function" ? p(cur) : p) };
      ref.current = next;
      return next;
    });
  }, []);

  const toast = (kind: ToastKind, text: string) => {
    const id = ++toastSeq;
    patch((c) => ({ toasts: [...c.toasts, { id, kind, text }] }));
    setTimeout(() => patch((c) => ({ toasts: c.toasts.filter((t) => t.id !== id) })), 3400);
  };

  const refresh = async () => {
    const st = await api.getState(DEMO);
    patch({ state: st, offline: false });
    return st;
  };

  const name = (id: string) => ref.current.state?.sites.find((s) => s.site_id === id)?.name ?? id;

  const announce = (h: number) => {
    for (const e of ref.current.events.filter((x) => x.sim_hour === h)) {
      if (e.type === "hazard_start") toast("fire", `Hour ${h}: ${e.hazard} reported near the county`);
      else if (e.type === "site_dark") toast("dark", `Signal lost: ${e.site_ids.map(name).join(" and ")}`);
      else if (e.type === "evacuee_arrival") toast("people", `+${e.people} evacuees arrive at ${name(e.site_id)}`);
    }
  };

  const markLost = (st: StateResponse, h: number) =>
    patch((c) => {
      const lost = { ...c.lostAt };
      for (const r of st.inventory) if (r.data_status === "stale" && lost[r.site_id] == null) lost[r.site_id] = h;
      return { lostAt: lost };
    });

  const confirm = async () => {
    const p = ref.current.parse;
    if (!p || !p.site_id || !p.supply_id || p.qty == null) return;
    await api.confirmFieldReport(DEMO, p);
    const after = await api.getStateAfterReport();
    if (after) patch({ state: after });
    else await refresh();
    const before = ref.current.lantern;
    const plan = await api.makePlan(DEMO, "lantern", true);
    patch({ lanternBefore: before, lantern: plan, confirmed: true, reignited: [p.site_id] });
    toast("live", `${name(p.site_id)} is back online`);
  };

  // One action per beat. `fast` skips pacing (used when jumping or replaying).
  const actions: Record<BeatId, (fast: boolean) => Promise<void>> = {
    intro: async () => {},
    calm: async () => {
      await api.reset(DEMO);
      patch(CLEAR);
      const [events] = await Promise.all([api.getEvents(DEMO).catch(() => [] as ScenarioEvent[]), refresh()]);
      patch({ events });
    },
    disaster: async (fast) => {
      if (fast) {
        await api.step(DEMO, 9);
        markLost(await refresh(), -1);
        return;
      }
      const my = runId.current;
      const start = ref.current.state?.sim_hour ?? 0;
      for (let h = start + 1; h <= 9; h++) {
        if (runId.current !== my) return;
        await api.step(DEMO, h);
        const st = await refresh();
        announce(h);
        markLost(st, h);
        await sleep(TICK_MS);
      }
    },
    naive: async () => {
      const plan = await api.makePlan(DEMO, "naive", true);
      const [log, single] = await Promise.all([
        api.getGateLog(plan.session_id).catch(() => [] as GateLogRow[]),
        api.getSingleCheck(plan.plan_id).catch(() => [] as SingleCheckRow[]),
      ]);
      patch({ naive: plan, naiveLog: log, single });
    },
    gate: async () => {},
    lantern: async () => {
      patch({ lantern: await api.makePlan(DEMO, "lantern", true) });
    },
    field: async () => {
      patch({ parse: await api.parseFieldReport(DEMO, SAMPLE_REPORT) });
    },
    recount: confirm,
    proof: async () => {
      if (!ref.current.chart) patch({ chart: await api.getProofChart() });
    },
    resilience: async () => {},
  };

  const guard = async (fn: () => Promise<void>) => {
    patch({ busy: true });
    try {
      await fn();
    } catch (e) {
      console.warn(e);
      patch({ offline: true });
    } finally {
      patch({ busy: false });
    }
  };

  /** Go to beat `target`. One step forward animates; anything else resets (if needed) and replays fast. */
  const goTo = async (target: number) => {
    const cur = ref.current;
    if (cur.busy || target < 0 || target >= BEATS.length || target === cur.beat) return;
    runId.current++;
    await guard(async () => {
      if (target === cur.beat + 1) {
        patch({ beat: target });
        await actions[BEATS[target].id](false);
        return;
      }
      let from = cur.beat + 1;
      if (target < cur.beat) {
        await actions.calm(true);
        from = 2;
      }
      for (let i = Math.max(from, 1); i <= target; i++) {
        patch({ beat: i });
        await actions[BEATS[i].id](true);
      }
      patch({ beat: target });
    });
  };

  // Explore mode: free clicking during Q&A.
  const explore = {
    parse: (text: string) => guard(async () => patch({ parse: await api.parseFieldReport(DEMO, text) })),
    confirm: () => guard(confirm),
    chart: () => guard(() => actions.proof(false)),
  };

  useEffect(() => {
    api
      .getConfig()
      .then((c) => patch({ cfg: c as PublicConfigX }))
      .catch(() =>
        patch({ cfg: { banner: "", planner_names: {}, bedrock_enabled: false, notify_enabled: false, mode: "offline" } }),
      );
    void guard(() => actions.calm(true));
    // load once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { d, goTo, explore, beat: BEATS[d.beat] };
}
