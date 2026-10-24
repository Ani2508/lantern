import { useEffect, useRef } from "react";
import { BEATS, type BeatId } from "../story/beats";

export interface KeyActions {
  next: () => void;
  prev: () => void;
  restart: () => void;
  mode: () => void;
  theme: () => void;
  gate: () => void;
  help: () => void;
  escape: () => void;
}

/** Presenter keyboard (and clicker: PgDn/PgUp). Ignored while typing in a field. */
export function useKeys(actions: KeyActions) {
  const ref = useRef(actions);
  ref.current = actions;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "TEXTAREA" || t.tagName === "INPUT")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const a = ref.current;
      const k = e.key;
      if (k === "ArrowRight" || k === " " || k === "PageDown") a.next();
      else if (k === "ArrowLeft" || k === "PageUp") a.prev();
      else if (k === "r" || k === "R") a.restart();
      else if (k === "e" || k === "E") a.mode();
      else if (k === "t" || k === "T") a.theme();
      else if (k === "s" || k === "S") a.gate();
      else if (k === "?") a.help();
      else if (k === "Escape") a.escape();
      else if (k === "f" || k === "F") {
        if (document.fullscreenElement) void document.exitFullscreen();
        else void document.documentElement.requestFullscreen?.();
      } else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

const DWELL_MS: Partial<Record<BeatId, number>> = {
  intro: 6500,
  calm: 6000,
  disaster: 9000,
  naive: 7000,
  gate: 11000,
  lantern: 9000,
  field: 8000,
  recount: 9000,
  proof: 13000,
};

/** ?autoplay=1 advances the story on a timer (backup for a recorded video). */
export function useAutoplay(beat: number, busy: boolean, next: () => void) {
  const on = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("autoplay") === "1";
  const nextRef = useRef(next);
  nextRef.current = next;
  useEffect(() => {
    if (!on || busy || beat >= BEATS.length - 1) return;
    const id = setTimeout(() => nextRef.current(), DWELL_MS[BEATS[beat].id] ?? 7000);
    return () => clearTimeout(id);
  }, [on, beat, busy]);
}
