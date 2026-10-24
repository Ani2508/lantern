/** Map layers drawn imperatively with Leaflet so CSS/WAAPI animations survive React re-renders. */
import L from "leaflet";
import { WifiOff } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useMap } from "react-leaflet";
import type { Decision, InventoryState, Site } from "../../api/types";
import { SITE_TYPE, siteAge, siteSpread, siteStatus } from "../../lib/labels";
import { token } from "../../lib/theme";

/** A Leaflet marker whose content is a React portal (DOM persists, so transitions animate). */
function PortalMarker({ at, z, children }: { at: [number, number]; z?: number; children: ReactNode }) {
  const map = useMap();
  const [el, setEl] = useState<HTMLElement | null>(null);
  const marker = useRef<L.Marker | null>(null);
  useEffect(() => {
    const m = L.marker(at, {
      icon: L.divIcon({ className: "site-host", html: "", iconSize: [0, 0] }),
      keyboard: false,
      zIndexOffset: z ?? 0,
    }).addTo(map);
    marker.current = m;
    setEl(m.getElement() ?? null);
    return () => {
      m.remove();
      marker.current = null;
    };
    // the marker is created once; position updates below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);
  useEffect(() => {
    marker.current?.setLatLng(at);
  }, [at]);
  return el ? createPortal(children, el) : null;
}

export function SiteBeacon(props: {
  site: Site;
  rows: InventoryState[];
  scout: boolean;
  justLost: boolean;
  reignite: boolean;
  dimmed: boolean;
  selected: boolean;
  onSelect?: (id: string) => void;
}) {
  const { site, rows } = props;
  const status = siteStatus(rows);
  const age = siteAge(rows);
  const spread = status === "live" ? 0 : siteSpread(rows);
  const halo = status === "live" || spread < 0.05 ? 0 : 56 + spread * 120;
  const { Icon } = SITE_TYPE[site.site_type];
  const scale = 0.92 + Math.min(site.people_served, 700) / 1800;
  const at = useRef<[number, number]>([site.lat, site.lon]);
  return (
    <PortalMarker at={at.current} z={props.scout ? 500 : 0}>
      <div
        className={`beacon ${status} ${props.reignite ? "reignite" : ""} ${props.dimmed ? "dimmed" : ""}`}
        onClick={() => props.onSelect?.(site.site_id)}
        title={site.name}
      >
        <div className="halo" style={{ width: halo, height: halo, opacity: halo ? 1 : 0 }} />
        {props.scout && <div className="scout" />}
        <div className="pulse" />
        <div
          className="core"
          style={{
            transform: `scale(${props.selected ? scale * 1.12 : scale})`,
            outline: props.selected ? "3px solid var(--amber)" : undefined,
            outlineOffset: 3,
          }}
        >
          <Icon />
        </div>
        {status !== "live" && (
          <div className="age">
            {status === "mixed" ? "partly live" : `${Math.round(age)}h old`}
          </div>
        )}
        {props.justLost && (
          <div className="lost">
            <WifiOff size={10} style={{ verticalAlign: -1 }} /> SIGNAL LOST
          </div>
        )}
        {props.scout && <div className="scout-tag">SCOUT</div>}
        <div className="label">
          {site.name}
          <small>{site.people_served.toLocaleString()} people</small>
        </div>
      </div>
    </PortalMarker>
  );
}

// ---- transfer arcs -----------------------------------------------------------------------------

function bezier(a: L.LatLng, b: L.LatLng, bend: number, n = 40): L.LatLng[] {
  const k = Math.cos((a.lat * Math.PI) / 180);
  const ax = a.lng * k;
  const bx = b.lng * k;
  const mx = (ax + bx) / 2;
  const my = (a.lat + b.lat) / 2;
  const dx = bx - ax;
  const dy = b.lat - a.lat;
  const cx = mx - dy * bend;
  const cy = my + dx * bend;
  const pts: L.LatLng[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * cx + t ** 2 * bx;
    const y = (1 - t) ** 2 * a.lat + 2 * (1 - t) * t * cy + t ** 2 * b.lat;
    pts.push(L.latLng(y, x / k));
  }
  return pts;
}

const COLOR: Record<Decision | "PENDING", string> = {
  APPROVE: "--approve",
  REVIEW: "--review",
  BLOCK: "--block",
  PENDING: "--muted",
};

export function TransferArc(props: {
  from: Site;
  to: Site;
  decision: Decision | "PENDING";
  label: string;
  bend: number;
  delay: number;
  theme: string;
}) {
  const map = useMap();
  const { decision, label, bend, delay } = props;
  const [fLat, fLon, tLat, tLon] = [props.from.lat, props.from.lon, props.to.lat, props.to.lon];
  useEffect(() => {
    const color = token(COLOR[decision]);
    const pts = bezier(L.latLng(fLat, fLon), L.latLng(tLat, tLon), bend);
    const line = L.polyline(pts, {
      color,
      weight: decision === "BLOCK" ? 5 : 4,
      opacity: decision === "PENDING" ? 0.55 : 0.95,
      className: "arc",
      interactive: false,
      dashArray: decision === "PENDING" ? "6 8" : undefined,
    }).addTo(map);
    const path = line.getElement() as SVGPathElement | undefined;
    const mid = pts[Math.floor(pts.length / 2)];
    const glyph = decision === "BLOCK" ? "✕ " : "";
    const tag = L.marker(mid, {
      icon: L.divIcon({
        className: "arc-label",
        html: `<span style="background:${color};opacity:0;transition:opacity 300ms">${glyph}${label}</span>`,
        iconSize: [0, 0],
      }),
      interactive: false,
      keyboard: false,
      zIndexOffset: 800,
    }).addTo(map);
    const timers: number[] = [];
    let anim: Animation | undefined;
    if (path && decision !== "PENDING") {
      const len = path.getTotalLength();
      path.style.strokeDasharray = `${len}`;
      path.style.strokeDashoffset = `${len}`;
      anim = path.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }], {
        duration: 850,
        delay,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        fill: "forwards",
      });
      anim.onfinish = () => {
        path.style.strokeDasharray = "";
        path.style.strokeDashoffset = "";
        anim?.cancel();
        if (decision === "APPROVE") path.classList.add("flow");
      };
    } else if (path) {
      path.style.opacity = "0";
      anim = path.animate([{ opacity: 0 }, { opacity: 0.55 }], { duration: 400, delay, fill: "forwards" });
    }
    timers.push(
      window.setTimeout(() => {
        const span = tag.getElement()?.querySelector("span");
        if (span) span.style.opacity = "1";
      }, delay + 600),
    );
    return () => {
      timers.forEach(clearTimeout);
      anim?.cancel();
      line.remove();
      tag.remove();
    };
  }, [map, fLat, fLon, tLat, tLon, decision, label, bend, delay, props.theme]);
  return null;
}
