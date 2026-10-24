import { motion } from "motion/react";
import { ArrowRight, Clock, ShieldX } from "lucide-react";
import type { SingleCheckRow } from "../../api/extraTypes";
import type { GateLogRow, Plan, Site, SupplyId } from "../../api/types";
import { RULES, SUPPLY, fmtQty, namer } from "../../lib/labels";
import { EASE } from "../../lib/motion";
import { DecisionChip } from "../ui";

export type GateView = "session" | "single";

/** The running-total meter: each transfer from the source stacks up against the session limit. */
function DrawMeter(props: { rows: GateLogRow[]; limit: number; unit: string; supply: SupplyId }) {
  const { rows, limit, unit, supply } = props;
  const total = rows.length ? rows[rows.length - 1].cumulative_draw_qty : 0;
  const max = Math.max(limit, total) * 1.18;
  const pct = (v: number) => (v / max) * 100;
  let prev = 0;
  return (
    <div className="meter">
      <div className="meter-track">
        {rows.map((r, i) => {
          const from = prev;
          prev = r.cumulative_draw_qty;
          const over = r.cumulative_draw_qty > limit;
          return (
            <motion.div
              key={r.transfer_id}
              className={`meter-seg ${over ? "over" : r.decision === "REVIEW" ? "warn" : ""}`}
              style={{ left: `${pct(from)}%` }}
              initial={{ width: 0 }}
              animate={{ width: `${pct(r.cumulative_draw_qty - from)}%` }}
              transition={{ duration: 0.55, delay: 0.35 + i * 0.6, ease: EASE }}
            >
              <span className="num">+{fmtQty(r.qty, supply)}</span>
            </motion.div>
          );
        })}
        <div className="meter-limit" style={{ left: `${pct(limit)}%` }}>
          <span>
            limit <b className="num">{fmtQty(limit, supply)}</b>
          </span>
        </div>
      </div>
      <div className="spread tiny muted">
        <span>Running total out of this source this session</span>
        <span className="num">
          {fmtQty(total, supply)} / {fmtQty(limit, supply)} {unit}
        </span>
      </div>
    </div>
  );
}

export function GatePanel(props: {
  plan: Plan;
  log: GateLogRow[];
  single: SingleCheckRow[];
  sites: Site[];
  view: GateView;
  onView: (v: GateView) => void;
}) {
  const { plan } = props;
  const name = namer(props.sites);
  const blocked = plan.transfers.find((t) => t.decision === "BLOCK");
  if (!blocked) return null;
  const row = props.log.find((r) => r.transfer_id === blocked.transfer_id);
  const sameSource = props.log
    .filter((r) => r.source_site_id === blocked.source_site_id && r.supply_id === blocked.supply_id)
    .sort((a, b) => a.cumulative_draw_qty - b.cumulative_draw_qty);
  const unit = SUPPLY[blocked.supply_id].unit;
  const singleBy = Object.fromEntries(props.single.map((s) => [s.transfer_id, s]));

  return (
    <motion.section
      className="panel gate-hero"
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.6, ease: EASE }}
    >
      <div className="gate-head">
        <motion.div
          className="gate-icon"
          initial={{ scale: 0.4, rotate: -20 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.15 }}
        >
          <ShieldX size={30} />
        </motion.div>
        <div>
          <div className="kicker" style={{ color: "var(--block)" }}>
            Safety gate · session-aware
          </div>
          <h2>Transfer blocked</h2>
        </div>
      </div>

      <div className="gate-what">
        <span>
          <span className="num">{fmtQty(blocked.qty, blocked.supply_id)}</span> {unit}{" "}
          {SUPPLY[blocked.supply_id].label.toLowerCase()}
        </span>
        <span className="route">
          {name(blocked.source_site_id)} <ArrowRight size={13} /> {name(blocked.dest_site_id)}
        </span>
      </div>

      <div className="gate-rules">
        {(blocked.rule_hits ?? []).map((r, i) => (
          <motion.div
            key={r}
            className="gate-rule"
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5 + i * 0.15, ease: EASE }}
          >
            <b>{RULES[r].short}</b>
            <span>{RULES[r].long}</span>
          </motion.div>
        ))}
      </div>

      {row && sameSource.length > 0 && <DrawMeter rows={sameSource} limit={row.cumulative_draw_limit} unit={unit} supply={blocked.supply_id} />}

      {row && (
        <p className="tiny dim gate-age">
          <Clock size={13} /> {name(blocked.source_site_id)}'s last count is{" "}
          <b className="num">{Math.round(row.source_report_age_h)} h</b> old. Worst case it holds{" "}
          <b className="num">{fmtQty(row.source_p05_before, blocked.supply_id)}</b> {unit}.
        </p>
      )}

      <div className="contrast">
        <div className="spread">
          <div className="kicker">Same three transfers, two kinds of check</div>
          <div className="seg small">
            {(["single", "session"] as const).map((v) => (
              <button key={v} className={props.view === v ? "on" : ""} onClick={() => props.onView(v)}>
                {props.view === v && <motion.span layoutId="gate-seg" className="pill" />}
                {v === "single" ? "One at a time" : "Session-aware"}
              </button>
            ))}
          </div>
        </div>
        <div className="contrast-rows">
          {plan.transfers.map((t, i) => {
            const d = props.view === "single" ? singleBy[t.transfer_id]?.decision : t.decision;
            return (
              <div key={t.transfer_id} className="contrast-row">
                <span className="num muted">#{i + 1}</span>
                <span className="grow">
                  {fmtQty(t.qty, t.supply_id)} {unit} → {name(t.dest_site_id)}
                </span>
                <motion.span key={`${props.view}-${d}`} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}>
                  {d ? <DecisionChip decision={d} /> : <span className="muted">—</span>}
                </motion.span>
              </div>
            );
          })}
        </div>
        <p className="tiny dim contrast-note">
          {props.view === "single"
            ? `Checked one by one, each transfer only gets a review flag. Nothing stops ${name(blocked.source_site_id)} being drained.`
            : "Lantern's gate watches the running total, so the third transfer is blocked."}
        </p>
      </div>
    </motion.section>
  );
}
