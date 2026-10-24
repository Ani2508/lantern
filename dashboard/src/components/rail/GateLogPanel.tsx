import type { GateLogRow, Site } from "../../api/types";
import { RULES, fmtQty, namer } from "../../lib/labels";
import { DecisionChip } from "../ui";

export function GateLogPanel({ rows, sites }: { rows: GateLogRow[]; sites: Site[] }) {
  const name = namer(sites);
  if (!rows.length) {
    return (
      <div className="panel pad">
        <h3>Audit trail</h3>
        <p className="muted" style={{ marginTop: 6 }}>
          Every transfer the gate checks is logged here. Run the naive plan to fill it.
        </p>
      </div>
    );
  }
  return (
    <section className="panel pad">
      <div className="kicker">Audit trail · DynamoDB</div>
      <h3 style={{ margin: "4px 0 10px" }}>Gate log</h3>
      <table className="log">
        <thead>
          <tr>
            <th>Decision</th>
            <th>Transfer</th>
            <th className="r">Running total</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.transfer_id}>
              <td>
                <DecisionChip decision={r.decision} compact />
              </td>
              <td>
                <div>
                  <span className="num">{fmtQty(r.qty, r.supply_id)}</span> {r.supply_id} · {name(r.source_site_id)} →{" "}
                  {name(r.dest_site_id)}
                </div>
                <div className="tiny muted">
                  {r.rule_hits.map((h) => RULES[h].short).join(" · ") || "All rules pass"} · data{" "}
                  {Math.round(r.source_report_age_h)} h old
                </div>
              </td>
              <td className="num r">
                {fmtQty(r.cumulative_draw_qty)} / {fmtQty(r.cumulative_draw_limit)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
