import L from "leaflet";
import { useEffect, useMemo, useRef, useState } from "react";
import { ImageOverlay, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { InventoryState, ScoutVisit, Site, Transfer } from "../../api/types";
import { SUPPLY, fmtQty } from "../../lib/labels";
import { SiteBeacon, TransferArc } from "./layers";

const CENTER: [number, number] = [37.31, -121.905];
const OFFLINE_BOUNDS: L.LatLngBoundsExpression = [
  [37.24, -122.0],
  [37.38, -121.82],
];
// Illustrative hazard area, north-east of the sites. Decorative only.
const FIRE_BOUNDS: [[number, number], [number, number]] = [
  [37.318, -121.888],
  [37.352, -121.846],
];

export interface MapArc {
  t: Transfer;
  shown: Transfer["decision"] | "PENDING";
}

function Camera({ sites, focus, leftPad }: { sites: Site[]; focus: string[]; leftPad: number }) {
  const map = useMap();
  const first = useRef(true);
  const key = `${sites.map((s) => s.site_id).join(",")}|${focus.join(",")}|${leftPad}`;
  const fit = useRef<(animate: boolean) => void>(() => {});
  fit.current = (animate: boolean) => {
    if (!sites.length) return;
    const chosen = focus.length ? sites.filter((s) => focus.includes(s.site_id)) : sites;
    const bounds = L.latLngBounds(chosen.map((s) => [s.lat, s.lon] as [number, number]));
    const opts = {
      // leftPad > 0 means a story caption sits bottom-left: keep the focus sites above it.
      paddingTopLeft: [80, 100] as [number, number],
      paddingBottomRight: [80, leftPad ? leftPad + 80 : 80] as [number, number],
      maxZoom: 15,
    };
    if (animate) map.flyToBounds(bounds, { ...opts, duration: 1.3 });
    else map.fitBounds(bounds, { ...opts, animate: false });
  };
  useEffect(() => {
    map.invalidateSize();
    fit.current(!first.current);
    if (sites.length) first.current = false;
    // `key` captures sites/focus/padding
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);
  useEffect(() => {
    const el = map.getContainer();
    const ro = new ResizeObserver(() => {
      map.invalidateSize();
      fit.current(false);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);
  return null;
}

function Fire({ show }: { show: boolean }) {
  const map = useMap();
  useEffect(() => {
    if (!show) return;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 200 160");
    svg.innerHTML = `
      <defs>
        <radialGradient id="fireg" cx="50%" cy="55%" r="55%">
          <stop offset="0%" stop-color="#ffb347" stop-opacity="0.75"/>
          <stop offset="45%" stop-color="#ff6a2b" stop-opacity="0.5"/>
          <stop offset="100%" stop-color="#b91c1c" stop-opacity="0"/>
        </radialGradient>
        <filter id="firef" x="-20%" y="-20%" width="140%" height="140%">
          <feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="3">
            <animate attributeName="baseFrequency" dur="9s" values="0.03;0.045;0.03" repeatCount="indefinite"/>
          </feTurbulence>
          <feDisplacementMap in="SourceGraphic" scale="26"/>
        </filter>
      </defs>
      <ellipse cx="100" cy="85" rx="88" ry="66" fill="url(#fireg)" filter="url(#firef)">
        <animate attributeName="rx" dur="4s" values="84;92;84" repeatCount="indefinite"/>
      </ellipse>`;
    const layer = L.svgOverlay(svg, FIRE_BOUNDS, { className: "fire-blob", interactive: false, opacity: 0 }).addTo(map);
    let raf = 0;
    const t0 = performance.now();
    const fade = (t: number) => {
      const k = Math.min(1, (t - t0) / 1600);
      layer.setOpacity(k);
      if (k < 1) raf = requestAnimationFrame(fade);
    };
    raf = requestAnimationFrame(fade);
    const b = L.latLngBounds(FIRE_BOUNDS);
    const tag = L.marker([b.getNorth() - 0.003, b.getCenter().lng], {
      icon: L.divIcon({ className: "fire-label", html: "<span>🔥 Illustrative fire area</span>", iconSize: [0, 0] }),
      interactive: false,
    }).addTo(map);
    return () => {
      cancelAnimationFrame(raf);
      layer.remove();
      tag.remove();
    };
  }, [map, show]);
  return null;
}

export function SiteMap(props: {
  sites: Site[];
  inventory: InventoryState[];
  arcs: MapArc[];
  scouts: ScoutVisit[];
  focus: string[];
  simHour: number;
  lostAt: Record<string, number>;
  reignited: string[];
  fire: boolean;
  dim: boolean;
  shake: number;
  theme: string;
  leftPad: number;
  selected?: string | null;
  onSelect?: (id: string) => void;
}) {
  const [offline, setOffline] = useState(false);
  const errors = useRef(0);
  const area = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = area.current;
    if (!el || !props.shake) return;
    el.classList.remove("map-shake");
    void el.offsetWidth; // restart the CSS animation
    el.classList.add("map-shake");
  }, [props.shake]);
  const byId = useMemo(() => Object.fromEntries(props.sites.map((s) => [s.site_id, s])), [props.sites]);
  const scoutIds = new Set(props.scouts.map((s) => s.site_id));
  // Esri Canvas basemaps: keyless, muted, with a separate label layer.
  const canvas = props.theme === "light" ? "World_Light_Gray" : "World_Dark_Gray";
  const esri = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";
  const tiles = `${esri}/${canvas}_Base/MapServer/tile/{z}/{y}/{x}`;
  const labels = `${esri}/${canvas}_Reference/MapServer/tile/{z}/{y}/{x}`;

  // Same source -> dest pairs get increasing bends so repeated transfers don't overlap.
  const seen: Record<string, number> = {};
  const arcEls = props.arcs.map(({ t, shown }, i) => {
    const a = byId[t.source_site_id];
    const b = byId[t.dest_site_id];
    if (!a || !b) return null;
    const pair = `${t.source_site_id}>${t.dest_site_id}`;
    const n = (seen[pair] = (seen[pair] ?? -1) + 1);
    return (
      <TransferArc
        key={`${t.transfer_id}:${shown}`}
        from={a}
        to={b}
        decision={shown ?? "PENDING"}
        label={`${fmtQty(t.qty, t.supply_id)} ${SUPPLY[t.supply_id].unit}`}
        bend={0.2 + n * 0.16}
        delay={shown === "BLOCK" ? 250 : i * 650}
        theme={props.theme}
      />
    );
  });

  return (
    <div className="map-area" ref={area}>
      <MapContainer center={CENTER} zoom={13} zoomSnap={0.25} zoomControl={false} attributionControl scrollWheelZoom>
        {!offline && (
          <TileLayer
            key={props.theme}
            url={tiles}
            maxNativeZoom={16}
            attribution="Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors"
            eventHandlers={{
              tileerror: () => {
                errors.current += 1;
                if (errors.current > 4) setOffline(true);
              },
            }}
          />
        )}
        {!offline && <TileLayer key={`${props.theme}-labels`} url={labels} maxNativeZoom={16} opacity={0.7} />}
        {offline && <ImageOverlay url="/basemap.svg" bounds={OFFLINE_BOUNDS} opacity={0.5} />}
        <Camera sites={props.sites} focus={props.focus} leftPad={props.leftPad} />
        <Fire show={props.fire} />
        {arcEls}
        {props.sites.map((s) => (
          <SiteBeacon
            key={s.site_id}
            site={s}
            rows={props.inventory.filter((r) => r.site_id === s.site_id)}
            scout={scoutIds.has(s.site_id)}
            justLost={props.lostAt[s.site_id] === props.simHour}
            reignite={props.reignited.includes(s.site_id)}
            dimmed={props.dim}
            selected={props.selected === s.site_id}
            onSelect={props.onSelect}
          />
        ))}
      </MapContainer>
      <div className="map-vignette" />
      {props.shake > 0 && <div className="edge-pulse" key={`edge-${props.shake}`} />}
      <div className="map-note">Synthetic sites on a real basemap · not real facilities</div>
    </div>
  );
}
