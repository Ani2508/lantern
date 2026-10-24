import { AnimatePresence } from "motion/react";
import { useEffect, useState } from "react";
import { Banner, Timeline, Toasts, TopBar, type Mode } from "./components/Chrome";
import { SiteMap, type MapArc } from "./components/map/SiteMap";
import { Rail, type Tab } from "./components/Rail";
import type { GateView } from "./components/rail/GatePanel";
import { useTheme } from "./lib/theme";
import { useDemo } from "./state/useDemo";
import { useAutoplay, useKeys } from "./state/useKeys";
import { BEATS, beatIndex } from "./story/beats";
import { Caption, Help, Intro } from "./story/Overlays";
import { ProofView } from "./story/ProofView";
import { Resilience } from "./story/Resilience";

export default function App() {
  const { theme, toggle } = useTheme();
  const { d, goTo, explore, beat } = useDemo();
  const [mode, setMode] = useState<Mode>("story");
  const [tab, setTab] = useState<Tab>("sites");
  const [gateView, setGateView] = useState<GateView>("session");
  const [help, setHelp] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [shake, setShake] = useState(0);
  const story = mode === "story";

  // The gate beat lands with a shake and a red edge pulse, after the blocked arc redraws.
  useEffect(() => {
    if (beat.id !== "gate") return;
    setGateView("session");
    const id = setTimeout(() => setShake((s) => s + 1), 500);
    return () => clearTimeout(id);
  }, [beat.id]);

  useEffect(() => {
    if (!story && tab === "results" && !d.chart) void explore.chart();
    // load the chart once when the Results tab opens
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [story, tab, d.chart]);

  const next = () => void goTo(d.beat + 1);
  useKeys({
    next,
    prev: () => void goTo(d.beat - 1),
    restart: () => void goTo(beatIndex("calm")),
    mode: () => setMode((m) => (m === "story" ? "explore" : "story")),
    theme: toggle,
    gate: () => setGateView((v) => (v === "session" ? "single" : "session")),
    help: () => setHelp((h) => !h),
    escape: () => setHelp(false),
  });
  useAutoplay(d.beat, d.busy, next);

  const sites = d.state?.sites ?? [];
  const inventory = d.state?.inventory ?? [];
  const hour = d.state?.sim_hour ?? 0;
  const hazardHour = d.events.find((e) => e.type === "hazard_start")?.sim_hour ?? 2;

  // Which plan the map draws.
  let arcs: MapArc[] = [];
  let scouts = d.lantern?.scouts ?? [];
  const showNaive = story ? beat.id === "naive" || beat.id === "gate" : ["naive", "gate", "log"].includes(tab);
  if (showNaive && d.naive) {
    const pending = story && beat.id === "naive";
    arcs = d.naive.transfers.map((t) => ({ t, shown: pending && t.decision === "BLOCK" ? "PENDING" : t.decision }));
    scouts = [];
  } else if (d.lantern && (!story || beatIndex(beat.id) >= beatIndex("lantern"))) {
    arcs = d.lantern.transfers.map((t) => ({ t, shown: t.decision }));
  }
  if (story && beat.id === "proof") arcs = [];
  if (story && beatIndex(beat.id) < beatIndex("lantern")) scouts = [];

  const overlay = story ? beat.id : tab === "results" ? "proof" : null;
  const railShown = !story || (beat.rail !== "none" && !["proof", "resilience"].includes(beat.id));

  return (
    <div className="app">
      <Banner />
      <TopBar
        hour={hour}
        inventory={inventory}
        cfg={d.cfg}
        offline={d.offline}
        mode={mode}
        onMode={setMode}
        theme={theme}
        onTheme={toggle}
        onHelp={() => setHelp(true)}
      />
      <main className={`stage ${railShown ? "" : "no-rail"}`}>
        <SiteMap
          sites={sites}
          inventory={inventory}
          arcs={arcs}
          scouts={scouts}
          focus={story ? beat.focus ?? [] : []}
          simHour={hour}
          lostAt={d.lostAt}
          reignited={d.reignited}
          fire={hour >= hazardHour}
          dim={overlay === "proof" || overlay === "resilience"}
          shake={shake}
          theme={theme}
          leftPad={story ? 230 : 0}
          selected={selected}
          onSelect={(id) => {
            setSelected((s) => (s === id ? null : id));
            if (!story) setTab("sites");
          }}
        />
        {railShown && (
          <Rail
            d={d}
            beat={beat}
            story={story}
            tab={tab}
            onTab={setTab}
            gateView={gateView}
            onGateView={setGateView}
            selected={selected}
            onSelect={setSelected}
            onParse={(t) => void explore.parse(t)}
            onConfirm={() => void explore.confirm()}
          />
        )}
        <Toasts toasts={d.toasts} />
        {story && beat.id !== "intro" && !["proof", "resilience"].includes(beat.id) && (
          <Caption beat={beat} index={d.beat} total={BEATS.length - 1} />
        )}
        <AnimatePresence>
          {overlay === "proof" && (
            <div className="stage-overlay" key="proof">
              <ProofView chart={d.chart} theme={theme} />
            </div>
          )}
          {overlay === "resilience" && (
            <div className="stage-overlay" key="res">
              <Resilience plan={d.lantern} sites={sites} />
            </div>
          )}
        </AnimatePresence>
      </main>
      <Timeline hour={hour} events={d.events} beat={d.beat} busy={d.busy} onBeat={(i) => void goTo(i)} />
      <Intro show={story && beat.id === "intro"} onStart={next} />
      <Help show={help} onClose={() => setHelp(false)} />
    </div>
  );
}
