import { useMemo, useState } from "react";
import type { Plan, PlannerId, ProofChart } from "../api/types";
import { PLANNER_NAMES, SUPPLIES, fmtQty } from "../lib/domain";

const PLANNER_COLOR: Record<PlannerId, string> = {
  lantern: "var(--gold)",
  naive: "var(--block)",
  equal_split: "var(--stale)",
};

export function ProofOverlay({ data, onClose }: { data: ProofChart | null; onClose: () => void }) {
  const [hoverX, setHoverX] = useState<number | null>(null);
  const series = useMemo(() => {
    const out: Record<PlannerId, { x: number; mean: number; lo: number; hi: number }[]> = {
      equal_split: [], naive: [], lantern: [],
    };
    if (!data) return out;
    const groups = new Map<string, number[]>();
    for (const r of data.rows) {
      const k = `${r.planner}|${r.data_loss_pct}`;
      groups.set(k, [...(groups.get(k) ?? []), r.shortage_hours]);
    }
    for (const [k, vals] of groups) {
      const [pl, x] = k.split("|");
      const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
      out[pl as PlannerId]?.push({ x: Number(x), mean, lo: Math.min(...vals), hi: Math.max(...vals) });
    }
    for (const s of Object.values(out)) s.sort((a, b) => a.x - b.x);
    return out;
  }, [data]);

  const W = 880, H = 420, L = 70, R = 190, T = 24, B = 60;
  const xs = series.lantern.map((p) => p.x);
  const xMax = Math.max(70, ...xs);
  const raw = Math.max(10, ...Object.values(series).flat().map((p) => p.mean)) * 1.1;
  const stepY = [10, 20, 25, 50, 100, 200].find((s) => raw / s <= 5) ?? 250;
  const yMax = Math.ceil(raw / stepY) * stepY;
  const X = (v: number) => L + (v / xMax) * (W - L - R);
  const Y = (v: number) => H - B - (v / yMax) * (H - T - B);
  const yTicks = Array.from({ length: yMax / stepY + 1 }, (_, i) => i * stepY);
  const order: PlannerId[] = ["equal_split", "naive", "lantern"];

  return (
    <div className="overlay" role="dialog" aria-label="Results across simulated outages">
      <div className="overlay-card proof">
        <button className="close" onClick={onClose} aria-label="Close results">Close</button>
        <h2>Shortages grow slowest with Lantern as sites go dark</h2>
        <p className="sub">
          Mean shortage-hours over 72 h, by share of sites with no live data. Three hazards,{" "}
          {data?.summary.seeds ?? "?"} runs per point{data?.summary.preliminary ? ", preliminary" : ""}. Simulation only.
        </p>
        <svg viewBox={`0 0 ${W} ${H}`} className="chart" onMouseLeave={() => setHoverX(null)}>
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={Y(t)} y2={Y(t)} className="grid" />
              <text x={L - 10} y={Y(t) + 4} className="axis" textAnchor="end">{t}</text>
            </g>
          ))}
          {xs.map((x) => (
            <g key={x}>
              <text x={X(x)} y={H - B + 22} className="axis" textAnchor="middle">{x}%</text>
              <rect x={X(x) - 20} y={T} width={40} height={H - T - B} fill="transparent" onMouseEnter={() => setHoverX(x)} />
            </g>
          ))}
          <text x={(L + W - R) / 2} y={H - 12} className="axis-title" textAnchor="middle">Sites with no live data</text>
          <text x={18} y={(T + H - B) / 2} className="axis-title" textAnchor="middle" transform={`rotate(-90 18 ${(T + H - B) / 2})`}>
            Shortage-hours
          </text>
          {hoverX !== null && <line x1={X(hoverX)} x2={X(hoverX)} y1={T} y2={H - B} className="cross" />}
          {order.map((pl, i) => {
            const pts = series[pl];
            if (!pts.length) return null;
            const d = pts.map((p, j) => `${j ? "L" : "M"}${X(p.x)} ${Y(p.mean)}`).join(" ");
            const last = pts[pts.length - 1];
            return (
              <g key={pl} className={`series ${pl}`}>
                <path d={d} stroke={PLANNER_COLOR[pl]} className="line" style={{ animationDelay: `${i * 450}ms` }} pathLength={1} />
                {pts.map((p) => (
                  <circle key={p.x} cx={X(p.x)} cy={Y(p.mean)} r={hoverX === p.x ? 6 : 3.5} fill={PLANNER_COLOR[pl]} />
                ))}
                <text x={X(last.x) + 8} y={Y(last.mean) + 4} fill={PLANNER_COLOR[pl]} className="series-label">
                  {PLANNER_NAMES[pl]}
                </text>
              </g>
            );
          })}
        </svg>
        {hoverX !== null && (
          <div className="readout">
            At {hoverX}% dark:{" "}
            {order.map((pl) => {
              const pt = series[pl].find((p) => p.x === hoverX);
              return pt ? (
                <span key={pl} style={{ color: PLANNER_COLOR[pl] }}>
                  {PLANNER_NAMES[pl]} {pt.mean.toFixed(1)} h{" "}
                </span>
              ) : null;
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export function ResilienceOverlay({ plan, siteName, onClose, fallbackUrl }: {
  plan: Plan | null;
  siteName: (id: string) => string;
  onClose: () => void;
  fallbackUrl?: string;
}) {
  const c = plan?.counts;
  const sms = plan
    ? `LANTERN h${String(plan.sim_hour).padStart(3, "0")}: ${c?.approve} approved, ${c?.review} review, ${c?.block} blocked.${
        plan.scouts.length ? ` Scout ${plan.scouts.map((s) => s.site_id).join(", ")}.` : ""
      }`
    : "No plan sent yet.";
  return (
    <div className="overlay offline" role="dialog" aria-label="Main app offline">
      <div className="outage-banner">Main app offline. The API was switched off for this test.</div>
      <div className="resilience">
        <div className="phone" aria-label="Text message on a coordinator's phone">
          <div className="phone-top">Messages</div>
          <div className="bubble">{sms}</div>
          <div className="bubble-meta">from Lantern alerts, just now</div>
        </div>
        <div className="fallback-page" aria-label="Static fallback page">
          <div className="fb-banner">SIMULATED DATA · synthetic scenario for demonstration only</div>
          <h3>Lantern, latest plan</h3>
          <p className="fb-meta">Hour {plan?.sim_hour ?? "–"}, served as a plain page with no app behind it</p>
          <ul>
            {(plan?.transfers ?? []).slice(0, 5).map((t) => (
              <li key={t.transfer_id}>
                <span className={`chip ${t.decision ?? "APPROVE"}`}>{t.decision ?? "APPROVE"}</span>
                {fmtQty(t.qty)} {SUPPLIES[t.supply_id].units} of {t.supply_id}, {siteName(t.source_site_id)} to {siteName(t.dest_site_id)}
              </li>
            ))}
          </ul>
          {plan?.scouts.map((s) => (
            <p key={s.scout_id} className="fb-scout">Scout {siteName(s.site_id)}</p>
          ))}
          {fallbackUrl && (
            <a href={fallbackUrl} target="_blank" rel="noreferrer">Open the real fallback page</a>
          )}
        </div>
      </div>
      <button className="close light" onClick={onClose}>Bring the app back</button>
    </div>
  );
}

export function Caption({ text, speaker, n, total }: { text: string; speaker: string; n: number; total: number }) {
  return (
    <div className="caption" key={n} aria-live="polite">
      <span className="caption-step">
        {n} of {total}
      </span>
      <p>{text}</p>
      <span className="caption-speaker">{speaker}</span>
    </div>
  );
}
