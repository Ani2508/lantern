/** App chrome: synthetic-data banner, top bar, bottom timeline, toasts. */
import { AnimatePresence, motion } from "motion/react";
import { Flame, Keyboard, Moon, Radio, Sparkles, Sun, Users, WifiOff, Zap } from "lucide-react";
import type { PublicConfigX, ScenarioEvent } from "../api/extraTypes";
import type { InventoryState } from "../api/types";
import { siteStatus } from "../lib/labels";
import { BANNER, PERSONA, simClock, type Theme } from "../lib/theme";
import type { Toast } from "../state/useDemo";
import { BEATS } from "../story/beats";

export type Mode = "story" | "explore";

export function Banner() {
  return (
    <div className="banner" role="note">
      <span className="dot" />
      {BANNER}
    </div>
  );
}

export function TopBar(props: {
  hour: number;
  inventory: InventoryState[];
  cfg: PublicConfigX | null;
  offline: boolean;
  mode: Mode;
  onMode: (m: Mode) => void;
  theme: Theme;
  onTheme: () => void;
  onHelp: () => void;
}) {
  const siteIds = [...new Set(props.inventory.map((r) => r.site_id))];
  const dark = siteIds.filter((id) => siteStatus(props.inventory.filter((r) => r.site_id === id)) !== "live").length;
  const llm = props.cfg?.bedrock_enabled
    ? props.cfg.llm_provider === "ollama"
      ? `Local LLM · ${props.cfg.llm_model ?? ""}`
      : "Bedrock on"
    : "LLM off · templates";
  return (
    <header className="topbar">
      <div className="brand">
        <span className="lantern-mark">
          <Zap size={14} strokeWidth={2.6} />
        </span>
        Lantern
      </div>
      <div className="scenario">
        <strong>Wildfire · fictional county</strong>
        <span className="tiny muted">{PERSONA}</span>
      </div>
      <div className="clock" title="Simulation clock">
        <span className="tiny muted">SIM</span>
        <span key={props.hour} className="h num roll">
          H+{String(props.hour).padStart(2, "0")}
        </span>
        <span className="num dim">{simClock(props.hour)}</span>
      </div>
      <div className="hud" title="Sites without live data">
        <Radio size={14} />
        <span className="label">Sites dark</span>
        <span className="num">
          <b>{dark}</b>/{siteIds.length || 5}
        </span>
        <span className="bar">
          <i style={{ width: `${(dark / Math.max(siteIds.length, 1)) * 100}%` }} />
        </span>
      </div>
      <div className="right">
        {props.offline && (
          <span className="chip BLOCK">
            <WifiOff aria-hidden /> API offline · showing last data
          </span>
        )}
        <span className="chip amber" title="Who writes the plain-English text">
          <Sparkles aria-hidden /> {llm}
        </span>
        <div className="seg">
          {(["story", "explore"] as const).map((m) => (
            <button key={m} className={props.mode === m ? "on" : ""} onClick={() => props.onMode(m)}>
              {props.mode === m && <motion.span layoutId="mode-pill" className="pill" />}
              {m === "story" ? "Story" : "Explore"}
            </button>
          ))}
        </div>
        <button className="btn icon ghost" onClick={props.onTheme} title="Toggle theme (T)" aria-label="Toggle theme">
          {props.theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
        </button>
        <button className="btn icon ghost" onClick={props.onHelp} title="Shortcuts (?)" aria-label="Shortcuts">
          <Keyboard size={17} />
        </button>
      </div>
    </header>
  );
}

const PIN_ICON = { hazard_start: Flame, site_dark: WifiOff, evacuee_arrival: Users } as const;
const PIN_TEXT = { hazard_start: "Wildfire", site_dark: "Sites dark", evacuee_arrival: "Evacuees" } as const;

export function Timeline(props: {
  hour: number;
  events: ScenarioEvent[];
  beat: number;
  busy: boolean;
  onBeat: (i: number) => void;
}) {
  const H = 9;
  const pins = props.events.filter((e) => e.type in PIN_ICON && e.sim_hour <= H);
  // spread pins that share an hour so labels don't collide
  const offsets: Record<number, number> = {};
  return (
    <footer className="timeline">
      {props.busy && <div className="busy-line" />}
      <div>
        <div className="kicker">
          Step {props.beat} of {BEATS.length - 1}
        </div>
        <div style={{ fontWeight: 700, fontSize: 15 }}>{BEATS[props.beat].short}</div>
      </div>
      <div className="hours">
        <div className="track" />
        <div className="fill" style={{ width: `${(props.hour / H) * 100}%` }} />
        {pins.map((e, i) => {
          const Icon = PIN_ICON[e.type as keyof typeof PIN_ICON];
          const n = (offsets[e.sim_hour] = (offsets[e.sim_hour] ?? -1) + 1);
          return (
            <div
              key={i}
              className={`pin ${props.hour >= e.sim_hour ? "hit" : ""}`}
              style={{ left: `calc(${(e.sim_hour / H) * 100}% + ${n} * var(--pin-gap))` }}
              title={PIN_TEXT[e.type as keyof typeof PIN_TEXT]}
            >
              <Icon /> <span className="txt">{PIN_TEXT[e.type as keyof typeof PIN_TEXT]}</span>
            </div>
          );
        })}
        {Array.from({ length: H + 1 }, (_, h) => (
          <span key={h} className={`hour-tick ${h <= props.hour ? "on" : ""}`} style={{ left: `${(h / H) * 100}%` }}>
            {h}
          </span>
        ))}
      </div>
      <div className="row">
        <div className="beats">
          {BEATS.map((b, i) => (
            <button
              key={b.id}
              className={`beat-dot ${i === props.beat ? "on" : i < props.beat ? "done" : ""}`}
              onClick={() => props.onBeat(i)}
              title={`${i}. ${b.short}`}
              aria-label={b.short}
            >
              <i />
            </button>
          ))}
        </div>
        <span className="tiny muted" style={{ marginLeft: 8 }}>
          <kbd>←</kbd> <kbd>→</kbd>
        </span>
      </div>
    </footer>
  );
}

const TOAST_ICON = { fire: Flame, dark: WifiOff, people: Users, live: Radio } as const;

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts">
      <AnimatePresence>
        {toasts.map((t) => {
          const Icon = TOAST_ICON[t.kind];
          return (
            <motion.div
              key={t.id}
              layout
              className={`panel toast ${t.kind}`}
              initial={{ opacity: 0, y: -16, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.97 }}
              transition={{ type: "spring", stiffness: 320, damping: 26 }}
            >
              <span className="ic">
                <Icon size={16} />
              </span>
              {t.text}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
