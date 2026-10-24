import { motion } from "motion/react";
import { useRef } from "react";
import type { InventoryState, Site, SupplyId } from "../../api/types";
import { SITE_TYPE, SUPPLY, SUPPLY_ORDER, rangeText, siteAge, siteStatus } from "../../lib/labels";
import { rise, stagger } from "../../lib/motion";
import { RangeBar } from "../ui";

function hoursLeft(r: InventoryState): string {
  const h = r.tts_p05_h;
  if (h == null) return "";
  if (h >= 72) return "72 h+";
  return `${h < 10 ? h.toFixed(1) : Math.round(h)} h`;
}

export function SitesPanel(props: {
  sites: Site[];
  inventory: InventoryState[];
  selected?: string | null;
  onSelect?: (id: string) => void;
}) {
  // A per-supply scale that only grows, so a collapsing range visibly shrinks instead of re-scaling.
  const scale = useRef<Record<string, number>>({});
  for (const r of props.inventory) {
    const top = Math.max(r.est_qty_p95 ?? 0, r.last_reported_qty) * 1.08;
    scale.current[r.supply_id] = Math.max(scale.current[r.supply_id] ?? 0, top);
  }
  if (!props.sites.length) {
    return (
      <div className="panel pad">
        <div className="kicker">Loading</div>
        <div className="skel" />
        <div className="skel" style={{ width: "60%" }} />
      </div>
    );
  }
  return (
    <motion.div className="stack" variants={stagger} initial="hidden" animate="show">
      {props.sites.map((s) => {
        const rows = props.inventory.filter((r) => r.site_id === s.site_id);
        const st = siteStatus(rows);
        const { Icon, label } = SITE_TYPE[s.site_type];
        const bySupply = Object.fromEntries(rows.map((r) => [r.supply_id, r])) as Record<SupplyId, InventoryState>;
        return (
          <motion.article
            key={s.site_id}
            variants={rise}
            layout
            className={`panel site-card ${st} ${props.selected === s.site_id ? "selected" : ""}`}
            onClick={() => props.onSelect?.(s.site_id)}
          >
            <div className="spread">
              <div className="row">
                <span className={`site-ic ${st}`}>
                  <Icon size={16} />
                </span>
                <div>
                  <strong>{s.name}</strong>
                  <div className="muted tiny">
                    {label} · <span className="num">{s.people_served.toLocaleString()}</span> people
                  </div>
                </div>
              </div>
              <span className={`chip ${st === "live" ? "live" : st === "stale" ? "stale" : "REVIEW"}`}>
                {st === "live" ? "Live" : st === "stale" ? `${Math.round(siteAge(rows))} h old` : "Partly live"}
              </span>
            </div>
            <div className="supplies">
              {SUPPLY_ORDER.filter((k) => bySupply[k]).map((k) => {
                const r = bySupply[k];
                const S = SUPPLY[k];
                return (
                  <div className="supply" key={k}>
                    <div className="spread tiny">
                      <span className="row" style={{ gap: 5 }}>
                        <S.Icon size={12} className="muted" />
                        {S.label}
                        {r.data_status === "stale" && <span className="muted">· estimate</span>}
                      </span>
                      <span className="num">
                        {rangeText(r)} <span className="muted">{S.unit}</span>
                        {k === "insulin" && <span className="muted"> · {hoursLeft(r)}</span>}
                      </span>
                    </div>
                    <RangeBar row={r} max={scale.current[k]} />
                  </div>
                );
              })}
            </div>
          </motion.article>
        );
      })}
    </motion.div>
  );
}
