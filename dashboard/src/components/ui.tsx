/** Small shared primitives: decision chip, animated number, uncertainty range bar, typewriter text. */
import { animate, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { Decision, InventoryState } from "../api/types";
import { DECISION } from "../lib/labels";

export function DecisionChip({ decision, compact }: { decision: Decision; compact?: boolean }) {
  const { label, Icon } = DECISION[decision];
  return (
    <span className={`chip ${decision}`}>
      <Icon aria-hidden />
      {compact ? decision : label}
    </span>
  );
}

/** Counts up (or down) to `value` whenever it changes. */
export function Stat({
  value,
  decimals = 0,
  duration = 1.1,
  prefix = "",
  suffix = "",
  className,
}: {
  value: number;
  decimals?: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}) {
  const el = useRef<HTMLSpanElement>(null);
  const last = useRef(0);
  useEffect(() => {
    const from = last.current;
    last.current = value;
    const ctl = animate(from, value, {
      duration,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        if (el.current) el.current.textContent = prefix + v.toLocaleString(undefined, {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }) + suffix;
      },
    });
    return () => ctl.stop();
  }, [value, decimals, duration, prefix, suffix]);
  return <span ref={el} className={`num ${className ?? ""}`} />;
}

/** p05..p95 band with a p50 tick, scaled to `max`. Animates when the band collapses after a fresh count. */
export function RangeBar({ row, max }: { row: InventoryState; max: number }) {
  const lo = row.est_qty_p05 ?? row.last_reported_qty;
  const hi = row.est_qty_p95 ?? row.last_reported_qty;
  const mid = row.est_qty_p50 ?? row.last_reported_qty;
  const pct = (v: number) => Math.max(0, Math.min(100, (v / Math.max(max, 0.01)) * 100));
  const live = row.data_status === "live";
  const narrow = pct(hi) - pct(lo) < 2;
  const left = narrow ? Math.max(0, pct(mid) - 1) : pct(lo);
  const width = narrow ? 2 : pct(hi) - pct(lo);
  const ease = [0.22, 1, 0.36, 1] as const;
  return (
    <div className="range" title={`${lo.toFixed(1)} – ${hi.toFixed(1)}`}>
      <motion.div
        className={`range-band ${live ? "live" : "stale"}`}
        initial={false}
        animate={{ left: `${left}%`, width: `${width}%` }}
        transition={{ duration: 0.9, ease }}
      />
      <motion.div
        className="range-tick"
        initial={false}
        animate={{ left: `${pct(mid)}%` }}
        transition={{ duration: 0.9, ease }}
      />
    </div>
  );
}

/** Reveals text a few characters at a time (re-runs when `text` changes). */
export function Typewriter({ text, cps = 90 }: { text: string; cps?: number }) {
  const [n, setN] = useState(0);
  useEffect(() => {
    setN(0);
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setN(text.length);
      return;
    }
    const step = Math.max(1, Math.round(cps / 30));
    const id = setInterval(() => {
      setN((v) => {
        if (v >= text.length) {
          clearInterval(id);
          return v;
        }
        return Math.min(text.length, v + step);
      });
    }, 1000 / 30);
    return () => clearInterval(id);
  }, [text, cps]);
  return (
    <span>
      {text.slice(0, n)}
      {n < text.length && <span className="caret" />}
    </span>
  );
}
