import type { GateLogRow, Site } from "../api/types";
import { SUPPLIES, fmtQty, unitFor } from "../lib/domain";

interface Props {
  rows: GateLogRow[];
  sites: Site[];
}

/** The one dramatic moment: draws from one source fill a meter, the last one spills past the limit. */
export function GateMoment({ rows, sites }: Props) {
  const firstBlock = rows.find((r) => r.decision === "BLOCK");
  if (!firstBlock) return null;
  const chain = rows.filter((r) => r.source_site_id === firstBlock.source_site_id && r.supply_id === firstBlock.supply_id);
  const upTo = chain.slice(0, chain.indexOf(firstBlock) + 1);
  const limit = firstBlock.cumulative_draw_limit ?? 0;
  const name = (id: string) => sites.find((s) => s.site_id === id)?.name ?? id;
  const unit = SUPPLIES[firstBlock.supply_id].units;

  const segs = upTo.map((r) => {
    const end = r.decision === "BLOCK" ? (r.cumulative_draw_qty ?? 0) + r.qty : r.cumulative_draw_qty ?? r.qty;
    return { r, start: end - r.qty, end };
  });
  const max = Math.max(limit * 1.35, ...segs.map((s) => s.end)) || 1;
  const pct = (v: number) => `${(v / max) * 100}%`;

  return (
    <section className="gate-moment" aria-live="polite">
      <header>
        <span className="chip BLOCK">BLOCK</span>
        <h3>The safety gate stopped this plan</h3>
      </header>
      <p className="gate-lede">
        {upTo.length} transfers of {firstBlock.supply_id} out of {name(firstBlock.source_site_id)}, whose last count is{" "}
        {fmtQty(firstBlock.source_report_age_h)} h old.
      </p>
      <div className="meter" role="img" aria-label={`Draws reach ${fmtQty(segs[segs.length - 1].end)} of a ${limit.toFixed(1)} ${unit} limit`}>
        <div className="meter-track">
          {segs.map(({ r, start, end }, i) => (
            <div
              key={r.transfer_id}
              className={`meter-seg ${r.decision}`}
              style={{ left: pct(start), width: pct(end - start), animationDelay: `${300 + i * 900}ms` }}
            >
              {(end - start) / max > 0.09 && <span>{fmtQty(r.qty)}</span>}
            </div>
          ))}
          <div className="meter-limit" style={{ left: pct(limit) }}>
            <span>limit {limit.toFixed(1)}</span>
          </div>
        </div>
        <div className="meter-legend">
          {segs.map(({ r }, i) => (
            <div key={r.transfer_id} className="meter-step" style={{ animationDelay: `${300 + i * 900}ms` }}>
              <span className={`chip ${r.decision}`}>{r.decision}</span>
              <span>
                {fmtQty(r.qty)} {unitFor(r.supply_id, r.qty)} to {name(r.dest_site_id)}
              </span>
            </div>
          ))}
        </div>
      </div>
      <p className="gate-reason" style={{ animationDelay: `${300 + segs.length * 900}ms` }}>
        {firstBlock.reason_text}
      </p>
    </section>
  );
}
