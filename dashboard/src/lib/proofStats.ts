import type { ProofChartResponse } from "../api/types";

type Means = Record<string, Record<string, number>>;

export interface ProofStats {
  level: number;
  vsNaivePct: number | null;
  lanternAt: number | null;
  naiveAt: number | null;
  unsafeCaught: number | null;
  unsafeTotal: number | null;
  coverage: number | null;
  replanMs: number | null;
  worlds: number | null;
  seeds: number | null;
}

const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Headline numbers from the eval summary, computed at runtime so they follow a re-run of eval. */
export function proofStats(chart: ProofChartResponse | null, level = 40): ProofStats {
  const s = (chart?.summary ?? {}) as Record<string, unknown>;
  const means = (s.shortage_hours_mean ?? {}) as Means;
  const lanternAt = num(means.lantern?.[String(level)]);
  const naiveAt = num(means.naive?.[String(level)]);
  const replan = num(s.replan_seconds_p50);
  return {
    level,
    vsNaivePct: lanternAt != null && naiveAt ? Math.round((1 - lanternAt / naiveAt) * 100) : null,
    lanternAt,
    naiveAt,
    unsafeCaught: num(s.unsafe_caught_session),
    unsafeTotal: num(s.unsafe_total),
    coverage: num(s.interval_coverage_90),
    replanMs: replan != null ? replan * 1000 : null,
    worlds: num(s.n_worlds),
    seeds: num(s.n_seeds),
  };
}
