import { useMemo } from "react";
import type { InventoryState, Plan, ScoutVisit, Site, SupplyId, Transfer } from "../api/types";
import { SITE_SUPPLIES, SUPPLIES, fmtQty, uncertainty } from "../lib/domain";
import { FIRE_ORIGIN, MAP_H, MAP_W, OPS, RIVER, ROADS, fireBlob, makeProjector, routePath, smoothPath } from "../lib/geo";
import { SiteGlyph } from "./Icons";

interface Props {
  sites: Site[];
  inventory: InventoryState[];
  hour: number;
  plan: Plan | null;
  supply: SupplyId | "all";
  hoverTransfer: string | null;
  onHoverTransfer: (id: string | null) => void;
  hoverSite: string | null;
  onHoverSite: (id: string | null) => void;
}

const DECISION_COLOR: Record<string, string> = {
  APPROVE: "var(--approve)",
  REVIEW: "var(--review)",
  BLOCK: "var(--block)",
};

export function MapView(p: Props) {
  const project = useMemo(() => makeProjector(p.sites), [p.sites]);
  const pos = useMemo(() => {
    const m: Record<string, [number, number]> = {};
    for (const s of p.sites) m[s.site_id] = project(s.lat, s.lon);
    return m;
  }, [p.sites, project]);

  const bySite = useMemo(() => {
    const m: Record<string, InventoryState[]> = {};
    for (const r of p.inventory) (m[r.site_id] ??= []).push(r);
    return m;
  }, [p.inventory]);

  const fireProgress = Math.max(0, Math.min(1, (p.hour - 1.5) / 7.5));
  const [fx, fy] = project(FIRE_ORIGIN.lat, FIRE_ORIGIN.lon);
  const ops = project(OPS.lat, OPS.lon);

  const transfers = (p.plan?.transfers ?? []).filter((t) => p.supply === "all" || t.supply_id === p.supply);
  const pairCount: Record<string, number> = {};

  return (
    <svg className="map" viewBox={`0 0 ${MAP_W} ${MAP_H}`} role="img" aria-label="Map of Riverbend County with five supply sites">
      <defs>
        <radialGradient id="fog" r="0.5">
          <stop offset="0" stopColor="#9E9E9E" stopOpacity="0.55" />
          <stop offset="0.55" stopColor="#9E9E9E" stopOpacity="0.22" />
          <stop offset="1" stopColor="#9E9E9E" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="glow" r="0.5">
          <stop offset="0" stopColor="#1E88E5" stopOpacity="0.55" />
          <stop offset="1" stopColor="#1E88E5" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="lamp" r="0.5">
          <stop offset="0" stopColor="#F2A900" stopOpacity="0.6" />
          <stop offset="1" stopColor="#F2A900" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="fire" r="0.5">
          <stop offset="0" stopColor="#FFB74D" stopOpacity="0.85" />
          <stop offset="0.45" stopColor="#E65100" stopOpacity="0.55" />
          <stop offset="1" stopColor="#C62828" stopOpacity="0" />
        </radialGradient>
        <filter id="flicker" x="-30%" y="-30%" width="160%" height="160%">
          <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="2" seed="4">
            <animate attributeName="baseFrequency" dur="9s" values="0.012;0.018;0.012" repeatCount="indefinite" />
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" scale="38" />
        </filter>
        {(["APPROVE", "REVIEW", "BLOCK"] as const).map((d) => (
          <marker key={d} id={`arrow-${d}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill={DECISION_COLOR[d]} />
          </marker>
        ))}
      </defs>

      {/* ground */}
      <rect width={MAP_W} height={MAP_H} fill="var(--night)" />
      <g className="terrain">
        <path d={smoothPath(RIVER.map(([la, lo]) => project(la, lo)))} className="river" />
        {ROADS.map((r, i) => (
          <path key={i} d={smoothPath(r.map(([la, lo]) => project(la, lo)))} className="road" />
        ))}
        <text x={36} y={MAP_H - 30} className="place">Riverbend County</text>
      </g>

      {/* fire */}
      {fireProgress > 0 && (
        <g className="fire" style={{ opacity: 0.35 + 0.65 * fireProgress }}>
          <path d={fireBlob(fx, fy, 0.35 + 0.95 * fireProgress)} fill="url(#fire)" filter="url(#flicker)" />
          <text x={fx - 40} y={fy - 70 - 60 * fireProgress} className="fire-label">Wildfire</text>
        </g>
      )}

      {/* light and fog around each site */}
      {p.sites.map((s) => {
        const rows = (bySite[s.site_id] ?? []).filter((r) => SITE_SUPPLIES[s.site_type].includes(r.supply_id));
        const stale = rows.some((r) => r.data_status === "stale");
        const u = Math.max(0, ...rows.map(uncertainty));
        const [x, y] = pos[s.site_id];
        return stale ? (
          <g key={s.site_id} className="fog">
            <circle cx={x} cy={y} r={46 + 120 * u} fill="url(#fog)" style={{ transition: "r 900ms ease" }} />
            <circle cx={x} cy={y} r={32 + 70 * u} className="fog-ring" />
          </g>
        ) : (
          <circle key={s.site_id} cx={x} cy={y} r={58} fill="url(#glow)" className="glow" />
        );
      })}

      {/* scouts: gold beams from the ops centre */}
      <g className="ops">
        <circle cx={ops[0]} cy={ops[1]} r={34} fill="url(#lamp)" />
        <circle cx={ops[0]} cy={ops[1]} r={9} className="ops-dot" />
        <text x={ops[0]} y={ops[1] + 30} className="ops-label">{OPS.name}</text>
      </g>
      {(p.plan?.scouts ?? []).map((sc: ScoutVisit, i) => {
        const [x, y] = pos[sc.site_id];
        const d = `M${ops[0]} ${ops[1]} L${x} ${y}`;
        return (
          <g key={sc.scout_id} className="scout">
            <path d={d} className="beam" style={{ animationDelay: `${i * 300}ms` }} />
            <circle r={5} className="walker">
              <animateMotion dur="3.2s" repeatCount="indefinite" path={d} begin={`${i * 0.4}s`} />
            </circle>
            <circle cx={x} cy={y} r={30} className="scout-ring" />
            <text x={x} y={y - 40} className="scout-label">Scout</text>
          </g>
        );
      })}

      {/* transfers */}
      {transfers.map((t: Transfer) => {
        const a = pos[t.source_site_id];
        const b = pos[t.dest_site_id];
        if (!a || !b) return null;
        const pair = `${t.source_site_id}>${t.dest_site_id}`;
        const k = (pairCount[pair] = (pairCount[pair] ?? -1) + 1);
        const { d, mid } = routePath(a, b, k);
        const dec = t.decision ?? "APPROVE";
        const w = 1.6 + Math.log10(t.qty + 1) * 0.9;
        const hot = p.hoverTransfer === t.transfer_id;
        return (
          <g
            key={t.transfer_id}
            className={`route ${dec} ${hot ? "hot" : ""} ${p.hoverTransfer && !hot ? "dim" : ""}`}
            onMouseEnter={() => p.onHoverTransfer(t.transfer_id)}
            onMouseLeave={() => p.onHoverTransfer(null)}
          >
            <path d={d} className="route-hit" />
            <path d={d} className="route-line" stroke={DECISION_COLOR[dec]} strokeWidth={w} markerEnd={dec === "BLOCK" ? undefined : `url(#arrow-${dec})`} />
            {dec === "BLOCK" && (
              <g transform={`translate(${mid[0]} ${mid[1]})`} className="block-x">
                <circle r={11} />
                <path d="M-4.5 -4.5L4.5 4.5M4.5 -4.5L-4.5 4.5" />
              </g>
            )}
            {hot && (
              <text x={mid[0]} y={mid[1] - 16} className="route-label">
                {fmtQty(t.qty)} {SUPPLIES[t.supply_id].units} of {t.supply_id}, {dec}
              </text>
            )}
          </g>
        );
      })}

      {/* sites */}
      {p.sites.map((s) => {
        const rows = bySite[s.site_id] ?? [];
        const stale = rows.some((r) => r.data_status === "stale");
        const age = Math.max(0, ...rows.map((r) => r.report_age_h));
        const people = rows[0]?.people_served ?? s.people_served;
        const [x, y] = pos[s.site_id];
        return (
          <g
            key={s.site_id}
            className={`site ${stale ? "stale" : "live"} ${p.hoverSite === s.site_id ? "hot" : ""}`}
            transform={`translate(${x} ${y})`}
            onMouseEnter={() => p.onHoverSite(s.site_id)}
            onMouseLeave={() => p.onHoverSite(null)}
            tabIndex={0}
            onFocus={() => p.onHoverSite(s.site_id)}
            onBlur={() => p.onHoverSite(null)}
          >
            <circle r={19} className="site-disc" />
            <SiteGlyph type={s.site_type} />
            <text y={38} className="site-name">{s.name}</text>
            <text y={55} className="site-status">
              {stale ? `no report for ${age} h` : `live, ${people.toLocaleString("en-US")} people`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
