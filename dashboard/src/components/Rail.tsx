import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import type { Demo } from "../state/useDemo";
import type { Beat } from "../story/beats";
import { FieldPanel } from "./rail/FieldPanel";
import { GateLogPanel } from "./rail/GateLogPanel";
import { GatePanel, type GateView } from "./rail/GatePanel";
import { PlanPanel } from "./rail/PlanPanel";
import { SitesPanel } from "./rail/SitesPanel";

export type Tab = "sites" | "naive" | "gate" | "lantern" | "field" | "log" | "results";
const TABS: [Tab, string][] = [
  ["sites", "Sites"],
  ["naive", "Naive AI"],
  ["gate", "Gate"],
  ["lantern", "Lantern"],
  ["field", "Field"],
  ["log", "Audit"],
  ["results", "Results"],
];

interface Props {
  d: Demo;
  beat: Beat;
  story: boolean;
  tab: Tab;
  onTab: (t: Tab) => void;
  gateView: GateView;
  onGateView: (v: GateView) => void;
  selected: string | null;
  onSelect: (id: string) => void;
  onParse: (text: string) => void;
  onConfirm: () => void;
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="panel pad">
      <h3>{title}</h3>
      <p className="muted" style={{ marginTop: 6 }}>
        {body}
      </p>
    </div>
  );
}

export function Rail(p: Props) {
  const { d } = p;
  const sites = d.state?.sites ?? [];
  const inventory = d.state?.inventory ?? [];
  const view = p.story ? p.beat.rail : p.tab;
  const focusSite = d.parse?.site_id ?? "S04";

  const sitesPanel = (only?: string) => (
    <SitesPanel
      key={only ? "focus-site" : "all-sites"}
      sites={only ? sites.filter((s) => s.site_id === only) : sites}
      inventory={inventory}
      selected={p.selected}
      onSelect={p.onSelect}
    />
  );
  const gate = d.naive && (
    <GatePanel
      plan={d.naive}
      log={d.naiveLog}
      single={d.single}
      sites={sites}
      view={p.gateView}
      onView={p.onGateView}
    />
  );
  const field = (
    <FieldPanel
      parse={d.parse}
      confirmed={d.confirmed}
      sites={sites}
      cfg={d.cfg}
      story={p.story}
      busy={d.busy}
      onParse={p.onParse}
      onConfirm={p.onConfirm}
    />
  );

  let body: ReactNode = null;
  if (p.story) {
    const recount = p.beat.id === "recount";
    if (view === "sites") body = sitesPanel();
    else if (view === "naive" && d.naive)
      body = <PlanPanel plan={d.naive} sites={sites} cfg={d.cfg} pendingBlock />;
    else if (view === "gate") body = gate;
    else if (view === "field" || recount) {
      // The focus site's card stays mounted across field -> recount so its range visibly collapses.
      body = (
        <>
          {sitesPanel(focusSite)}
          {recount && d.lantern ? (
            <PlanPanel plan={d.lantern} sites={sites} cfg={d.cfg} before={d.lanternBefore} />
          ) : (
            field
          )}
        </>
      );
    } else if (view === "lantern" && d.lantern) body = <PlanPanel plan={d.lantern} sites={sites} cfg={d.cfg} />;
  } else {
    if (view === "sites") body = sitesPanel();
    else if (view === "naive")
      body = d.naive ? (
        <PlanPanel plan={d.naive} sites={sites} cfg={d.cfg} />
      ) : (
        <Empty title="No naive plan yet" body="Jump to step 3 on the timeline to run it." />
      );
    else if (view === "gate")
      body = gate || <Empty title="Nothing blocked yet" body="The gate card appears once the naive plan runs." />;
    else if (view === "lantern")
      body = d.lantern ? (
        <PlanPanel plan={d.lantern} sites={sites} cfg={d.cfg} before={d.lanternBefore} />
      ) : (
        <Empty title="No Lantern plan yet" body="Jump to step 5 on the timeline to run it." />
      );
    else if (view === "field") body = field;
    else if (view === "log") body = <GateLogPanel rows={d.naiveLog} sites={sites} />;
    else if (view === "results") body = <Empty title="Results" body="The full results view is open over the map." />;
  }

  return (
    <aside className="rail">
      {!p.story && (
        <nav className="tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={p.tab === id ? "on" : ""} onClick={() => p.onTab(id)}>
              {label}
              {p.tab === id && <motion.span layoutId="tab-underline" className="underline" />}
            </button>
          ))}
        </nav>
      )}
      <div className="rail-body scroll">
        <AnimatePresence mode="popLayout">
          <motion.div
            key={p.story ? (p.beat.id === "recount" ? "field" : view) : view}
            className="stack"
            initial={{ opacity: 0, x: 24 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -24 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            {body}
          </motion.div>
        </AnimatePresence>
      </div>
    </aside>
  );
}
