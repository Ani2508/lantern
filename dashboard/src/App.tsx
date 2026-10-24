import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api/client";
import type { GateLogRow, Plan, PlannerId, ProofChart, ScenarioState, SupplyId } from "./api/types";
import { InventoryStrip } from "./components/InventoryStrip";
import { MapView } from "./components/MapView";
import { Caption, ProofOverlay, ResilienceOverlay } from "./components/Overlays";
import { PlanPanel } from "./components/PlanPanel";
import { Timeline, TopBar } from "./components/TopBar";
import { narrator, sfx } from "./lib/audio";
import { BANNER, clockLabel } from "./lib/domain";
import { DARK_HOUR, STORY } from "./lib/story";

const params = new URLSearchParams(window.location.search);
const RECORD = params.has("record");
const NARRATE = params.has("narrate");
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export default function App() {
  const [data, setData] = useState<ScenarioState | null>(null);
  const [hour, setHour] = useState(0);
  const [plans, setPlans] = useState<Partial<Record<PlannerId, Plan>>>({});
  const [shown, setShown] = useState<PlannerId | null>(null);
  const [gateRows, setGateRows] = useState<GateLogRow[]>([]);
  const [showGate, setShowGate] = useState(false);
  const [supply, setSupply] = useState<SupplyId | "all">("all");
  const [overlay, setOverlay] = useState<"proof" | "resilience" | null>(null);
  const [proof, setProof] = useState<ProofChart | null>(null);
  const [step, setStep] = useState(0);
  const [stepReady, setStepReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [captions, setCaptions] = useState(true);
  const [busy, setBusy] = useState<PlannerId | null>(null);
  const [moving, setMoving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoverTransfer, setHoverTransfer] = useState<string | null>(null);
  const [hoverSite, setHoverSite] = useState<string | null>(null);
  const [narrate, setNarrate] = useState(NARRATE);
  const [sound, setSound] = useState(NARRATE || params.has("sound"));
  const [awaitClick, setAwaitClick] = useState(RECORD && NARRATE);
  const speech = useRef<Promise<void>>(Promise.resolve());
  const stepStart = useRef(0);
  const run = useRef(0);
  const hourRef = useRef(0);

  useEffect(() => {
    narrator.enabled = narrate;
    if (!narrate) narrator.cancel();
  }, [narrate]);
  useEffect(() => {
    sfx.enabled = sound;
  }, [sound]);

  const loadHour = useCallback(async (h: number) => {
    const at = await api.step(h);
    hourRef.current = at;
    setHour(at);
    setData(await api.state());
    return at;
  }, []);

  /** Walk the clock hour by hour so fog, fire and badges visibly change. */
  const moveTo = useCallback(
    async (target: number, msPerHour: number, id: number) => {
      setMoving(true);
      try {
        if (target < hourRef.current || msPerHour === 0 || reducedMotion) {
          await loadHour(target);
          return;
        }
        for (let h = hourRef.current + 1; h <= target; h++) {
          if (run.current !== id) return;
          if (h === DARK_HOUR) sfx.dark();
          await loadHour(h);
          await sleep(msPerHour);
        }
      } finally {
        setMoving(false);
      }
    },
    [loadHour],
  );

  const plansHour = useRef<number>(-1);
  const runPlan = useCallback(
    async (pl: PlannerId, opts: { quiet?: boolean } = {}) => {
      setError(null);
      if (plansHour.current !== hourRef.current) {
        setPlans({});
        plansHour.current = hourRef.current;
      }
      setBusy(pl);
      try {
        const plan = await api.plan(pl);
        setPlans((p) => ({ ...p, [pl]: plan }));
        setShown(pl);
        if (plan.counts.block > 0) {
          const rows = await api.gateLog(plan.session_id);
          setGateRows(rows.filter((r) => r.plan_id === plan.plan_id).sort((a, b) => a.transfer_id.localeCompare(b.transfer_id)));
          if (!opts.quiet) setShowGate(true);
        } else if (!opts.quiet) {
          setShowGate(false);
        }
        return plan;
      } catch (e) {
        setError((e as Error).message);
        return null;
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const goStep = useCallback(
    async (n: number) => {
      const s = STORY[n - 1];
      if (!s) return;
      const id = ++run.current;
      setStep(n);
      setStepReady(false);
      stepStart.current = performance.now();
      speech.current = narrator.speak(s.narration); // runs alongside the animation
      setOverlay(null);
      setShowGate(false);
      const animate = n === 2 && hourRef.current < s.hour ? 650 : 0;
      if (hourRef.current !== s.hour) {
        setShown(null);
        await moveTo(s.hour, animate, id);
      }
      if (run.current !== id) return;
      if (s.planner) {
        await runPlan(s.planner, { quiet: true });
      } else {
        setShown(null);
      }
      if (run.current !== id) return;
      setSupply(s.supply);
      setShowGate(s.gate);
      if (s.overlay === "proof") setProof(await api.proof());
      setOverlay(s.overlay);
      if (n === 4) window.setTimeout(() => run.current === id && sfx.alarm(), 2100);
      if (n === 5) sfx.chime();
      if (n === 7) {
        sfx.powerDown();
        window.setTimeout(() => run.current === id && sfx.ping(), 1100);
      }
      setStepReady(true);
    },
    [moveTo, runPlan],
  );

  // first load
  useEffect(() => {
    (async () => {
      await api.reset();
      await loadHour(0);
      if (RECORD && !NARRATE) {
        await sleep(1500);
        setPlaying(true);
      }
    })().catch((e) => setError((e as Error).message));
  }, [loadHour]);

  // auto-play
  useEffect(() => {
    if (!playing) return;
    if (step === 0) {
      goStep(1);
      return;
    }
    if (!stepReady) return;
    if (step >= STORY.length) {
      setPlaying(false);
      return;
    }
    let cancelled = false;
    (async () => {
      await speech.current;
      // at least the step's normal time on screen; with a voice, also 1.4 s after it finishes
      const elapsed = performance.now() - stepStart.current;
      await sleep(Math.max(narrator.enabled ? 1400 : 0, STORY[step - 1].dwellMs - elapsed));
      if (!cancelled) goStep(step + 1);
    })();
    return () => {
      cancelled = true;
    };
  }, [playing, step, stepReady, goStep]);

  // keyboard: arrows step, space plays, C toggles captions, Escape closes overlays
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") goStep(Math.min(STORY.length, step + 1));
      else if (e.key === "ArrowLeft") goStep(Math.max(1, step - 1));
      else if (e.key === " ") {
        e.preventDefault();
        setPlaying((p) => !p);
      } else if (e.key.toLowerCase() === "c") setCaptions((c) => !c);
      else if (e.key.toLowerCase() === "n") setNarrate((v) => !v);
      else if (e.key.toLowerCase() === "s") setSound((v) => !v);
      else if (e.key === "Escape") setOverlay(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goStep, step]);

  const onScrub = async (h: number) => {
    run.current++;
    narrator.cancel();
    setPlaying(false);
    setStep(0);
    setShowGate(false);
    setOverlay(null);
    if (h !== hourRef.current) setShown(null);
    await loadHour(h).catch((e) => setError((e as Error).message));
  };

  const plan = shown ? plans[shown] ?? null : null;
  const canPlan = api.planHours === "any" || api.planHours.includes(hour);
  const siteName = (id: string) => data?.sites.find((s) => s.site_id === id)?.name ?? id;
  const current = step ? STORY[step - 1] : null;

  if (!data) {
    return (
      <div className="loading">
        <div className="banner">{BANNER}</div>
        <p>{error ? `Could not load the scenario: ${error}` : "Loading Riverbend County…"}</p>
      </div>
    );
  }

  return (
    <div className={`app ${RECORD ? "record" : ""}`}>
      <div className="banner">{BANNER}</div>
      <TopBar
        hour={hour}
        sites={data.sites}
        inventory={data.inventory}
        mode={api.mode}
        step={step}
        playing={playing}
        onStep={(n) => {
          setPlaying(false);
          goStep(n);
        }}
        onPlay={() => setPlaying((p) => !p)}
        record={RECORD}
      />
      <Timeline hour={hour} maxHour={api.mode === "mock" ? api.maxHour : 23} onScrub={onScrub} disabled={moving || playing} />

      <main className="stage">
        <div className="map-wrap">
          <MapView
            sites={data.sites}
            inventory={data.inventory}
            hour={hour}
            plan={plan}
            supply={supply}
            hoverTransfer={hoverTransfer}
            onHoverTransfer={setHoverTransfer}
            hoverSite={hoverSite}
            onHoverSite={setHoverSite}
          />
          <div className="legend" aria-hidden="true">
            <span><i className="lg live" />fresh count</span>
            <span><i className="lg fog" />old count, fog grows with age</span>
            <span><i className="lg gold" />scout</span>
          </div>
          {!RECORD && (
            <div className="dock">
              <button onClick={async () => { setProof(await api.proof()); setOverlay("proof"); }}>Results chart</button>
              <button onClick={() => setOverlay("resilience")} disabled={!plans.lantern}>Simulate app offline</button>
              <button onClick={() => setCaptions((c) => !c)} aria-pressed={captions}>Captions</button>
              {narrator.supported && (
                <button onClick={() => setNarrate((v) => !v)} aria-pressed={narrate} className={narrate ? "on" : ""}>
                  {narrate ? "Narration on" : "Narration off"}
                </button>
              )}
              <button onClick={() => setSound((v) => !v)} aria-pressed={sound} className={sound ? "on" : ""}>
                {sound ? "Sound on" : "Sound off"}
              </button>
            </div>
          )}
        </div>
        <PlanPanel
          plan={plan}
          sites={data.sites}
          supply={supply}
          onSupply={setSupply}
          showGate={showGate && shown === "naive"}
          gateRows={gateRows}
          busy={busy}
          canPlan={canPlan && !moving}
          planHint={`Plans in the offline demo data are for ${clockLabel(9)}. Move the timeline to the end, or press Play the story.`}
          onRunPlan={(pl) => {
            run.current++;
            narrator.cancel();
            setPlaying(false);
            setStep(0);
            runPlan(pl);
          }}
          hoverTransfer={hoverTransfer}
          onHoverTransfer={setHoverTransfer}
        />
      </main>

      <InventoryStrip sites={data.sites} inventory={data.inventory} hoverSite={hoverSite} onHoverSite={setHoverSite} />

      {captions && current && (
        <Caption text={current.caption} speaker={RECORD ? "" : current.speaker} n={current.n} total={STORY.length} />
      )}

      {overlay === "proof" && <ProofOverlay data={proof} onClose={() => setOverlay(null)} />}
      {overlay === "resilience" && (
        <ResilienceOverlay
          plan={plans.lantern ?? null}
          siteName={siteName}
          onClose={() => setOverlay(null)}
          fallbackUrl={import.meta.env.VITE_FALLBACK_URL as string | undefined}
        />
      )}
      {awaitClick && (
        <button
          className="start-screen"
          onClick={() => {
            setAwaitClick(false);
            setPlaying(true);
          }}
        >
          <span>Click anywhere to start the narrated demo</span>
          <small>Start your screen recording first. Sound and voice need one click to begin.</small>
        </button>
      )}
      {error && (
        <div className="toast" role="alert">
          {error}
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}
    </div>
  );
}
