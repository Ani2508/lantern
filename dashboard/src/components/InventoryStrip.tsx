import type { InventoryState, Site } from "../api/types";
import { SITE_SUPPLIES, SUPPLIES, fmtQty } from "../lib/domain";
import { SiteGlyph } from "./Icons";

interface Props {
  sites: Site[];
  inventory: InventoryState[];
  hoverSite: string | null;
  onHoverSite: (id: string | null) => void;
}

/** Each bar: the shaded band is where stock may really be (worst case to best case); the
 *  tick is the most likely value; the hollow mark is the last count the site sent. */
export function InventoryStrip({ sites, inventory, hoverSite, onHoverSite }: Props) {
  return (
    <section className="strip" aria-label="Stock at each site">
      {sites.map((s) => {
        const rows = inventory
          .filter((r) => r.site_id === s.site_id && SITE_SUPPLIES[s.site_type].includes(r.supply_id))
          .sort((a, b) => a.supply_id.localeCompare(b.supply_id));
        const stale = rows.some((r) => r.data_status === "stale");
        return (
          <div
            key={s.site_id}
            className={`stock ${stale ? "stale" : "live"} ${hoverSite === s.site_id ? "hot" : ""}`}
            onMouseEnter={() => onHoverSite(s.site_id)}
            onMouseLeave={() => onHoverSite(null)}
          >
            <div className="stock-head">
              <svg width="22" height="22" viewBox="-12 -12 24 24" aria-hidden="true">
                <SiteGlyph type={s.site_type} />
              </svg>
              <strong>{s.name}</strong>
              <span className="badge">{stale ? `${Math.max(...rows.map((r) => r.report_age_h))} h old` : "live"}</span>
            </div>
            {rows.map((r) => {
              const lo = r.est_qty_p05 ?? r.last_reported_qty;
              const mid = r.est_qty_p50 ?? r.last_reported_qty;
              const hi = r.est_qty_p95 ?? r.last_reported_qty;
              const scale = Math.max(hi, r.last_reported_qty, 1) * 1.08;
              const pc = (v: number) => `${Math.min(100, (v / scale) * 100)}%`;
              const left = r.tts_p05_h ?? 72;
              const sup = SUPPLIES[r.supply_id];
              return (
                <div key={r.supply_id} className={`stock-row ${left < 12 ? "urgent" : ""}`}>
                  <span className="sup">{r.supply_id}</span>
                  <div className="bar" aria-hidden="true">
                    <div className="band" style={{ left: pc(lo), width: `calc(${pc(hi)} - ${pc(lo)})` }} />
                    <div className="tick" style={{ left: pc(mid) }} />
                    {r.data_status === "stale" && <div className="last" style={{ left: pc(r.last_reported_qty) }} />}
                  </div>
                  <span className="val">
                    {Math.abs(hi - lo) < 0.5 ? fmtQty(mid) : `${fmtQty(lo)}–${fmtQty(hi)}`} <small>{sup.units}</small>
                  </span>
                  <span className="left">{left >= 72 ? "72 h+" : `${Math.floor(left)} h left`}</span>
                </div>
              );
            })}
          </div>
        );
      })}
    </section>
  );
}
