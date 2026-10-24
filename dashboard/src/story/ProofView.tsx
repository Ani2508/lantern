import { motion } from "motion/react";
import type { ReactNode } from "react";
import { CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ProofChartResponse } from "../api/types";
import { Stat } from "../components/ui";
import { EASE } from "../lib/motion";
import { proofStats } from "../lib/proofStats";
import { PLANNER_NAMES, token } from "../lib/theme";

// Draw order: the planner that trusts stale data first, Lantern last.
const ORDER = ["naive", "equal_split", "lantern"];
const COLOR_TOKEN: Record<string, string> = { naive: "--block", equal_split: "--stale", lantern: "--amber" };

function series(chart: ProofChartResponse) {
  const levels = [...new Set(chart.rows.map((r) => r.data_loss_pct))].sort((a, b) => a - b);
  return levels.map((lv) => {
    const row: Record<string, number> = { data_loss_pct: lv };
    for (const p of ORDER) {
      const xs = chart.rows.filter((r) => r.planner === p && r.data_loss_pct === lv).map((r) => r.shortage_hours);
      if (!xs.length) continue;
      row[p] = Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10;
    }
    return row;
  });
}

export function ProofView({ chart, theme }: { chart: ProofChartResponse | null; theme: string }) {
  if (!chart || !chart.rows.length) {
    return (
      <div className="proof">
        <div className="panel pad">No evaluation results yet. Run python scripts/tasks.py eval --seeds 5.</div>
      </div>
    );
  }
  const s = proofStats(chart, 40);
  const data = series(chart);
  const planners = ORDER.filter((p) => chart.rows.some((r) => r.planner === p));
  const color = (p: string) => token(COLOR_TOKEN[p] ?? "--text");
  const axis = { fontFamily: "JetBrains Mono", fontSize: 12, fill: token("--muted") };
  const equalAt = (chart.summary as { shortage_hours_mean?: Record<string, Record<string, number>> }).shortage_hours_mean
    ?.equal_split?.["40"];

  const stats = [
    s.vsNaivePct != null && {
      big: <Stat value={s.vsNaivePct} prefix="−" suffix="%" />,
      label: `shortage-hours vs naive AI with ${s.level}% of sites dark`,
    },
    s.unsafeCaught != null && {
      big: (
        <>
          <Stat value={s.unsafeCaught} />
          <span className="of">/{s.unsafeTotal?.toLocaleString()}</span>
        </>
      ),
      label: "unsafe transfers stopped by the session-aware gate",
    },
    s.coverage != null && {
      big: <Stat value={s.coverage * 100} decimals={0} suffix="%" />,
      label: "of outcomes fall inside the 90% forecast range",
    },
    s.replanMs != null && { big: <Stat value={s.replanMs} decimals={1} suffix=" ms" />, label: "median time to re-plan" },
  ].filter(Boolean) as { big: ReactNode; label: string }[];

  return (
    <motion.div
      className="proof"
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      transition={{ duration: 0.7, ease: EASE }}
    >
      <div className="proof-stats">
        {stats.map((st, i) => (
          <motion.div
            key={st.label}
            className="panel pad proof-stat"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.12, ease: EASE, duration: 0.5 }}
          >
            <div className="big">{st.big}</div>
            <div className="dim">{st.label}</div>
          </motion.div>
        ))}
      </div>
      <motion.div
        className="panel pad proof-chart"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5, duration: 0.6 }}
      >
        <div className="spread">
          <div>
            <div className="kicker">Simulation results</div>
            <h3>Shortage-hours as more sites go dark</h3>
          </div>
          <div className="legend">
            {planners.map((p) => (
              <span key={p} className="row">
                <i style={{ background: color(p) }} />
                {PLANNER_NAMES[p] ?? p}
              </span>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height="100%" key={theme}>
          <ComposedChart data={data} margin={{ top: 16, right: 24, left: 0, bottom: 8 }}>
            <CartesianGrid stroke={token("--border")} vertical={false} />
            <XAxis dataKey="data_loss_pct" tick={axis} tickFormatter={(v) => `${v}%`} stroke={token("--border-strong")} />
            <YAxis tick={axis} stroke={token("--border-strong")} width={48} />
            <Tooltip
              contentStyle={{
                background: token("--surface-solid"),
                border: `1px solid ${token("--border-strong")}`,
                borderRadius: 10,
                fontFamily: "Inter Variable, Inter, sans-serif",
              }}
              labelFormatter={(v) => `${v}% of sites dark`}
              formatter={(v, n) => [`${v} h`, PLANNER_NAMES[String(n)] ?? n]}
            />
            <ReferenceLine
              x={40}
              stroke={token("--amber")}
              strokeDasharray="4 4"
              label={{ value: "today's scenario", fill: token("--amber"), fontSize: 11, position: "insideTopRight" }}
            />
            {planners.map((p, i) => (
              <Line
                key={p}
                type="monotone"
                dataKey={p}
                name={p}
                stroke={color(p)}
                strokeWidth={p === "lantern" ? 3.5 : 2.5}
                dot={{ r: 3, strokeWidth: 0, fill: color(p) }}
                animationBegin={400 + i * 900}
                animationDuration={1100}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
        <p className="tiny muted">
          Each point is the mean of {s.seeds ?? "several"} seeds ({chart.rows.length} simulated runs in total). Equal split is shown for reference
          {equalAt != null ? ` (${Math.round(equalAt)} h at 40%)` : ""}. Simulation only, not a field result.
        </p>
      </motion.div>
    </motion.div>
  );
}
