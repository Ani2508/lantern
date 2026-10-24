import { useState } from "react";
import type { GateLogRow, Plan, PlannerId, Site, SupplyId } from "../api/types";
import { PLANNER_NAMES, fmtQty, unitFor } from "../lib/domain";
import { GateMoment } from "./GateMoment";

interface Props {
  plan: Plan | null;
  sites: Site[];
  supply: SupplyId | "all";
  onSupply: (s: SupplyId | "all") => void;
  showGate: boolean;
  gateRows: GateLogRow[];
  busy: PlannerId | null;
  canPlan: boolean;
  planHint: string;
  onRunPlan: (p: PlannerId) => void;
  hoverTransfer: string | null;
  onHoverTransfer: (id: string | null) => void;
}

const SUPPLY_TABS: (SupplyId | "all")[] = ["all", "water", "food", "insulin"];

export function PlanPanel(p: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const name = (id: string) => p.sites.find((s) => s.site_id === id)?.name ?? id;
  const transfers = (p.plan?.transfers ?? []).filter((t) => p.supply === "all" || t.supply_id === p.supply);

  return (
    <aside className="rail">
      <div className="run">
        <p className="rail-title">Plan a delivery round</p>
        <div className="run-buttons">
          {(["naive", "lantern", "equal_split"] as PlannerId[]).map((pl) => (
            <button
              key={pl}
              className={`run-btn ${pl} ${p.plan?.planner === pl ? "active" : ""}`}
              disabled={!p.canPlan || p.busy !== null}
              onClick={() => p.onRunPlan(pl)}
              aria-pressed={p.plan?.planner === pl}
            >
              {p.busy === pl ? "Planning…" : PLANNER_NAMES[pl]}
            </button>
          ))}
        </div>
        {!p.canPlan && <p className="hint">{p.planHint}</p>}
      </div>

      {p.showGate && <GateMoment rows={p.gateRows} sites={p.sites} />}

      {p.plan ? (
        <div className="plan" key={p.plan.plan_id}>
          <div className="plan-head">
            <h2 className={p.plan.planner}>{PLANNER_NAMES[p.plan.planner]}</h2>
            <div className="counts">
              <span className="chip APPROVE">{p.plan.counts.approve} APPROVE</span>
              <span className="chip REVIEW">{p.plan.counts.review} REVIEW</span>
              <span className="chip BLOCK">{p.plan.counts.block} BLOCK</span>
            </div>
            <p className="summary">{p.plan.summary_text}</p>
          </div>

          <div className="tabs" role="tablist" aria-label="Filter by supply">
            {SUPPLY_TABS.map((s) => (
              <button key={s} role="tab" aria-selected={p.supply === s} className={p.supply === s ? "on" : ""} onClick={() => p.onSupply(s)}>
                {s === "all" ? "All supplies" : s[0].toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>

          <ol className="transfers">
            {transfers.map((t, i) => {
              const isOpen = open === t.transfer_id;
              return (
                <li
                  key={t.transfer_id}
                  className={`transfer ${p.hoverTransfer === t.transfer_id ? "hot" : ""}`}
                  style={{ animationDelay: `${i * 70}ms` }}
                  onMouseEnter={() => p.onHoverTransfer(t.transfer_id)}
                  onMouseLeave={() => p.onHoverTransfer(null)}
                >
                  <button aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : t.transfer_id)}>
                    <span className="qty">
                      {fmtQty(t.qty)} <small>{unitFor(t.supply_id, t.qty)}</small>
                    </span>
                    <span className="what">
                      <strong>{t.supply_id[0].toUpperCase() + t.supply_id.slice(1)}</strong>
                      <span>
                        {name(t.source_site_id)} to {name(t.dest_site_id)}
                      </span>
                    </span>
                    {t.decision && <span className={`chip ${t.decision}`}>{t.decision}</span>}
                  </button>
                  {isOpen && <p className="why">{t.explanation_text || t.reason_text}</p>}
                </li>
              );
            })}
            {transfers.length === 0 && <li className="empty">No {p.supply} moves in this plan.</li>}
          </ol>

          {p.plan.scouts.length > 0 && (
            <div className="scouts">
              <p className="rail-title">Send someone to count</p>
              {p.plan.scouts.map((s) => (
                <div key={s.scout_id} className="scout-card">
                  <strong>{name(s.site_id)}</strong>
                  <p>{s.reason_text}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="plan-empty">
          <p>No plan yet. Pick a planner above to see what it would move, and what the safety gate thinks of it.</p>
        </div>
      )}
    </aside>
  );
}
