import type { InventoryState, Site } from "../api/types";
import { clockLabel } from "../lib/domain";
import { EVENTS, STORY } from "../lib/story";
import { LanternMark } from "./Icons";

interface TopProps {
  hour: number;
  sites: Site[];
  inventory: InventoryState[];
  mode: "mock" | "live";
  step: number;
  playing: boolean;
  onStep: (n: number) => void;
  onPlay: () => void;
  record: boolean;
}

export function TopBar(p: TopProps) {
  const reporting = p.sites.filter((s) => !p.inventory.some((r) => r.site_id === s.site_id && r.data_status === "stale"));
  return (
    <header className="top">
      <div className="brand">
        <LanternMark />
        <div>
          <h1>Lantern</h1>
          <p>Riverbend County wildfire, synthetic scenario</p>
        </div>
      </div>

      <div className="clock" aria-live="polite">
        <span className="time">{clockLabel(p.hour)}</span>
        <span className="hour">hour {p.hour}</span>
      </div>

      <div className="health" title="Sites that sent a count this hour">
        <div className="dots">
          {p.sites.map((s) => (
            <span key={s.site_id} className={reporting.includes(s) ? "on" : "off"} />
          ))}
        </div>
        <span>
          {reporting.length} of {p.sites.length} sites reporting
        </span>
      </div>

      {!p.record && (
        <nav className="story-nav" aria-label="Demo story">
          <button className="play" onClick={p.onPlay} aria-pressed={p.playing}>
            {p.playing ? "Pause" : p.step === 0 ? "Play the story" : "Resume"}
          </button>
          <ol>
            {STORY.map((s) => (
              <li key={s.n}>
                <button
                  className={p.step === s.n ? "on" : p.step > s.n ? "done" : ""}
                  onClick={() => p.onStep(s.n)}
                  title={s.title}
                  aria-current={p.step === s.n ? "step" : undefined}
                >
                  {s.n}
                </button>
              </li>
            ))}
          </ol>
          <span className={`mode ${p.mode}`}>{p.mode === "mock" ? "Offline demo data" : "Live"}</span>
        </nav>
      )}
    </header>
  );
}

interface TimelineProps {
  hour: number;
  maxHour: number;
  onScrub: (h: number) => void;
  disabled: boolean;
}

export function Timeline({ hour, maxHour, onScrub, disabled }: TimelineProps) {
  const pct = (h: number) => `${(h / maxHour) * 100}%`;
  return (
    <div className="timeline">
      <label htmlFor="scrub">Time</label>
      <div className="track">
        <div className="fill" style={{ width: pct(hour) }} />
        {EVENTS.filter((e) => e.hour <= maxHour).map((e, i) => (
          <span key={e.hour} className={`event ${i % 2 ? "below" : ""} ${e.hour === maxHour ? "end" : ""}`} style={{ left: pct(e.hour) }} title={e.label}>
            <i />
            <em>{e.label}</em>
          </span>
        ))}
        <input
          id="scrub"
          type="range"
          min={0}
          max={maxHour}
          step={1}
          value={hour}
          disabled={disabled}
          onChange={(e) => onScrub(Number(e.target.value))}
          aria-valuetext={`hour ${hour}, ${clockLabel(hour)}`}
        />
      </div>
      <span className="ends">
        {clockLabel(0)}–{clockLabel(maxHour)}
      </span>
    </div>
  );
}
