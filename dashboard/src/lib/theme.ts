import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";
const KEY = "lantern.theme";

export const BANNER = "Simulated data · synthetic scenario for demonstration only";
export const PERSONA = "Maya Ortiz · County Supply Coordinator";
export const SIM_START = Date.parse("2026-11-07T08:00:00Z");

export const PLANNER_NAMES: Record<string, string> = {
  equal_split: "Equal split",
  naive: "Naive AI (trusts old data)",
  lantern: "Lantern",
};

function initial(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved;
  } catch {
    /* storage blocked: fall through */
  }
  return "dark";
}

/** Theme lives on <html data-theme>; CSS tokens do the rest. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initial);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      /* ignore */
    }
  }, [theme]);
  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  return { theme, toggle };
}

/** Read a CSS token (for Leaflet and Recharts, which need literal colors). */
export function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || "#888";
}

export function simClock(hour: number): string {
  const d = new Date(SIM_START + hour * 3600_000);
  return d.toISOString().slice(11, 16);
}
