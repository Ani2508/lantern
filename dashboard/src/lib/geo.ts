// Fictional "Riverbend County" map. Site positions come from the data (synthetic lat/lon);
// the river, roads and fire are drawn around them. Not to scale.
import type { Site } from "../api/types";

export const MAP_W = 1000;
export const MAP_H = 640;

export interface Projector {
  (lat: number, lon: number): [number, number];
}

export function makeProjector(sites: Site[]): Projector {
  const lats = sites.map((s) => s.lat);
  const lons = sites.map((s) => s.lon);
  const [lat0, lat1] = [Math.min(...lats), Math.max(...lats)];
  const [lon0, lon1] = [Math.min(...lons), Math.max(...lons)];
  const padX = 200;
  const padTop = 90;
  const padBottom = 150; // keep sites clear of the caption
  return (lat, lon) => [
    padX + ((lon - lon0) / (lon1 - lon0 || 1)) * (MAP_W - 2 * padX),
    padTop + ((lat1 - lat) / (lat1 - lat0 || 1)) * (MAP_H - padTop - padBottom),
  ];
}

/** Operations centre where scouts leave from (synthetic). */
export const OPS = { lat: 38.535, lon: -121.548, name: "Ops centre" };
/** Where the fire starts (synthetic). */
export const FIRE_ORIGIN = { lat: 38.572, lon: -121.425 };

export const RIVER: [number, number][] = [
  [38.6, -121.6], [38.57, -121.56], [38.545, -121.52], [38.52, -121.49],
  [38.497, -121.478], [38.475, -121.455], [38.46, -121.42], [38.43, -121.39],
];

export const ROADS: [number, number][][] = [
  [[38.5576, -121.5], [38.5, -121.5], [38.45, -121.53]],
  [[38.5, -121.5], [38.54, -121.45]],
  [[38.5, -121.5], [38.48, -121.47]],
  [[38.535, -121.548], [38.5, -121.5]],
  [[38.5576, -121.5], [38.54, -121.45]],
];

export function smoothPath(points: [number, number][]): string {
  if (points.length < 2) return "";
  let d = `M${points[0][0].toFixed(1)} ${points[0][1].toFixed(1)}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [x, y] = points[i];
    const [nx, ny] = points[i + 1];
    d += ` Q${x.toFixed(1)} ${y.toFixed(1)} ${((x + nx) / 2).toFixed(1)} ${((y + ny) / 2).toFixed(1)}`;
  }
  const last = points[points.length - 1];
  d += ` T${last[0].toFixed(1)} ${last[1].toFixed(1)}`;
  return d;
}

/** Curved route between two points; k separates parallel routes on the same pair. */
export function routePath(a: [number, number], b: [number, number], k: number): { d: string; mid: [number, number] } {
  const [x1, y1] = a;
  const [x2, y2] = b;
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  const len = Math.hypot(x2 - x1, y2 - y1) || 1;
  const off = 26 + 14 * k;
  const cx = mx + (-(y2 - y1) / len) * off;
  const cy = my + ((x2 - x1) / len) * off;
  // point on the curve at t = 0.5
  const mid: [number, number] = [0.25 * x1 + 0.5 * cx + 0.25 * x2, 0.25 * y1 + 0.5 * cy + 0.25 * y2];
  return { d: `M${x1} ${y1} Q${cx} ${cy} ${x2} ${y2}`, mid };
}

/** Irregular fire front, radius scaled by s. */
export function fireBlob(cx: number, cy: number, s: number): string {
  const lobes = [1.0, 0.82, 1.12, 0.9, 1.25, 0.86, 1.05, 0.78, 1.18, 0.92, 1.08, 0.84];
  const pts: [number, number][] = lobes.map((r, i) => {
    const a = (i / lobes.length) * Math.PI * 2;
    return [cx + Math.cos(a) * r * 150 * s, cy + Math.sin(a) * r * 120 * s];
  });
  return smoothPath([...pts, pts[0], pts[1]]) + " Z";
}
