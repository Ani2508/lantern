import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, GitCompareArrows, Loader2, Radar, Sparkles } from "lucide-react";
import type { PublicConfigX } from "../../api/extraTypes";
import type { Plan, Site } from "../../api/types";
import { RULES, SUPPLY, fmtQty, namer, voiLabel } from "../../lib/labels";
import { rise, stagger } from "../../lib/motion";
import { PLANNER_NAMES } from "../../lib/theme";
import { DecisionChip, Stat, Typewriter } from "../ui";

function writerLabel(plan: Plan, cfg: PublicConfigX | null): string {
  if (plan.explanation_source !== "bedrock") return "Template text";
  const who = cfg?.llm_provider === "ollama" ? "Local LLM" : "Amazon Bedrock";
  return cfg?.llm_model ? `${who} · ${cfg.llm_model}` : who;
}

/** Transfers in the new plan that come from a source the old plan didn't use. */
function rerouted(before: Plan | null, after: Plan): number {
  if (!before) return 0;
  const old = new Set(before.transfers.map((t) => t.source_site_id));
  return after.transfers.filter((t) => !old.has(t.source_site_id)).length;
}

export function PlanPanel(props: {
  plan: Plan;
  sites: Site[];
  cfg: PublicConfigX | null;
  /** Hide the BLOCK verdict until the gate beat. */
  pendingBlock?: boolean;
  before?: Plan | null;
}) {
  const { plan } = props;
  const name = namer(props.sites);
  const changed = rerouted(props.before ?? null, plan);
  const isLantern = plan.planner === "lantern";
  return (
    <motion.section className="panel pad plan" variants={rise} initial="hidden" animate="show" key={plan.plan_id}>
      <div className="spread">
        <div className="kicker">Plan · hour {plan.sim_hour}</div>
        <span className="chip amber" title="Who wrote the explanation text">
          <Sparkles aria-hidden /> {writerLabel(plan, props.cfg)}
        </span>
      </div>
      <h3 className={`plan-title ${isLantern ? "lantern" : "naive"}`}>{PLANNER_NAMES[plan.planner] ?? plan.planner}</h3>

      <div className="counts">
        <div className="count approve">
          <Stat value={plan.counts.approve} />
          <span>approved</span>
        </div>
        <div className="count review">
          <Stat value={plan.counts.review} />
          <span>review</span>
        </div>
        <div className="count block">
          <Stat value={props.pendingBlock ? 0 : plan.counts.block} />
          <span>blocked</span>
        </div>
      </div>

      <AnimatePresence>
        {changed > 0 && (
          <motion.div className="diff" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
            <GitCompareArrows size={15} /> Plan changed: {changed} transfer{changed > 1 ? "s" : ""} now drawn from the
            freshly counted site
          </motion.div>
        )}
      </AnimatePresence>

      {!props.pendingBlock && (
        <p className="summary">
          <Typewriter text={plan.summary_text} />
        </p>
      )}

      <motion.div className="xfers" variants={stagger} initial="hidden" animate="show">
        {plan.transfers.map((t) => {
          const pending = props.pendingBlock && t.decision === "BLOCK";
          const S = SUPPLY[t.supply_id];
          return (
            <motion.div key={t.transfer_id} variants={rise} className={`xfer ${pending ? "pending" : t.decision ?? ""}`}>
              <div className="spread">
                <span className="row xfer-qty">
                  <S.Icon size={14} />
                  <span className="num">{fmtQty(t.qty, t.supply_id)}</span> {S.unit} {S.label.toLowerCase()}
                </span>
                {pending ? (
                  <span className="chip">
                    <Loader2 className="spin" aria-hidden /> Checking
                  </span>
                ) : (
                  t.decision && <DecisionChip decision={t.decision} />
                )}
              </div>
              <div className="route">
                {name(t.source_site_id)} <ArrowRight size={12} /> {name(t.dest_site_id)}
                <span className="muted num"> · {t.distance_km} km</span>
              </div>
              {!pending && t.decision !== "APPROVE" && (t.rule_hits ?? []).length > 0 && (
                <div className="row wrap rules">
                  {(t.rule_hits ?? []).map((r) => (
                    <span key={r} className={`rule ${t.decision}`}>
                      {RULES[r].short}
                    </span>
                  ))}
                </div>
              )}
            </motion.div>
          );
        })}
      </motion.div>

      {plan.scouts.length > 0 && (
        <div className="scouts">
          <div className="kicker">Scout visits</div>
          {plan.scouts.map((s) => (
            <motion.div key={s.scout_id} className="scout-row" variants={rise} initial="hidden" animate="show">
              <span className="scout-ic">
                <Radar size={15} />
              </span>
              <div className="grow">
                <div className="spread">
                  <strong>{name(s.site_id)}</strong>
                  <span className="tiny muted">value of a count: {voiLabel(s.voi_score)}</span>
                </div>
                <div className="tiny dim">{s.reason_text}</div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
      <div className="tiny muted num foot">
        {plan.data_loss_pct}% of sites dark · planned in {plan.runtime_ms} ms
      </div>
    </motion.section>
  );
}
