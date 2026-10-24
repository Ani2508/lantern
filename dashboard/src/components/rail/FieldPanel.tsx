import { motion } from "motion/react";
import { AlertTriangle, Check, CheckCircle2, MessageSquareText, Sparkles } from "lucide-react";
import { useState } from "react";
import type { PublicConfigX } from "../../api/extraTypes";
import type { FieldReportParse, Site } from "../../api/types";
import { SUPPLY, fmtQty, namer } from "../../lib/labels";
import { EASE } from "../../lib/motion";
import { SAMPLE_REPORT } from "../../story/beats";

function parserLabel(p: FieldReportParse, cfg: PublicConfigX | null) {
  if (p.parser_source !== "bedrock") return "Rules parser";
  const who = cfg?.llm_provider === "ollama" ? "Local LLM" : "Amazon Bedrock";
  return cfg?.llm_model ? `${who} · ${cfg.llm_model}` : who;
}

export function FieldPanel(props: {
  parse: FieldReportParse | null;
  confirmed: boolean;
  sites: Site[];
  cfg: PublicConfigX | null;
  story: boolean;
  busy: boolean;
  onParse: (text: string) => void;
  onConfirm: () => void;
}) {
  const [text, setText] = useState(SAMPLE_REPORT);
  const p = props.parse;
  const name = namer(props.sites);
  const fields = p
    ? [
        ["Site", name(p.site_id)],
        ["Supply", p.supply_id ? SUPPLY[p.supply_id].label : "—"],
        ["Count", p.qty != null && p.supply_id ? `${fmtQty(p.qty, p.supply_id)} ${SUPPLY[p.supply_id].unit}` : "—"],
        ["Confidence", `${Math.round(p.confidence * 100)}%`],
      ]
    : [];
  const ready = !!p && !!p.site_id && !!p.supply_id && p.qty != null;

  return (
    <section className="panel pad field">
      <div className="kicker">Field report</div>
      <div className="phone-thread">
        <div className="sender">
          <MessageSquareText size={13} /> Volunteer scout · SMS
        </div>
        <motion.div
          className="sms"
          initial={{ opacity: 0, y: 16, scale: 0.94 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 22 }}
        >
          {props.story ? p?.source_text ?? SAMPLE_REPORT : text}
        </motion.div>
      </div>

      {!props.story && (
        <div className="stack" style={{ gap: 8 }}>
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          <div className="row">
            <button className="btn" disabled={props.busy} onClick={() => props.onParse(text)}>
              <Sparkles size={14} /> Parse
            </button>
            <button className="btn primary" disabled={props.busy || !ready || props.confirmed} onClick={props.onConfirm}>
              <Check size={14} /> Confirm count
            </button>
          </div>
        </div>
      )}

      {p && (
        <div className="parse">
          <div className="spread">
            <span className="tiny muted">Structured by</span>
            <span className="chip amber">
              <Sparkles aria-hidden /> {parserLabel(p, props.cfg)}
            </span>
          </div>
          {fields.map(([k, v], i) => (
            <motion.div
              key={`${p.field_report_id}-${k}`}
              className="parse-field"
              initial={{ opacity: 0, x: -12 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.25 + i * 0.28, duration: 0.35, ease: EASE }}
            >
              <span className="muted">{k}</span>
              <span className="row">
                <b>{v}</b>
                <motion.span
                  className="tick"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.45 + i * 0.28, type: "spring", stiffness: 400, damping: 15 }}
                >
                  <Check size={11} />
                </motion.span>
              </span>
            </motion.div>
          ))}
          {p.problems.length > 0 && (
            <div className="row tiny" style={{ color: "var(--review)" }}>
              <AlertTriangle size={13} /> {p.problems.join(" ")}
            </div>
          )}
          {p.needs_confirmation && !props.confirmed && (
            <div className="tiny" style={{ color: "var(--review)" }}>
              Low confidence: held until a coordinator confirms.
            </div>
          )}
          {props.confirmed ? (
            <motion.div className="confirmed" initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}>
              <CheckCircle2 size={16} /> Confirmed by Maya and ingested as a fresh report
            </motion.div>
          ) : (
            props.story && (
              <div className="tiny muted">
                Press <kbd>→</kbd> to confirm the count
              </div>
            )
          )}
        </div>
      )}
    </section>
  );
}
