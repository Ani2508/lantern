import { motion } from "motion/react";
import { MessageSquareText, Power, Zap } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { Plan, Site } from "../api/types";
import { SUPPLY, fmtQty, namer } from "../lib/labels";
import { EASE } from "../lib/motion";

function fallbackUrl(): string {
  const env = import.meta.env.VITE_FALLBACK_URL as string | undefined;
  return env || `${window.location.origin}/fallback/`;
}

export function Resilience({ plan, sites }: { plan: Plan | null; sites: Site[] }) {
  const url = fallbackUrl();
  const [qr, setQr] = useState("");
  const name = namer(sites);
  useEffect(() => {
    QRCode.toDataURL(url, { margin: 1, width: 220, color: { dark: "#0b0f14", light: "#ffffff" } })
      .then(setQr)
      .catch(() => setQr(""));
  }, [url]);
  const first = plan?.transfers[0];
  const sms = first
    ? `LANTERN H+${plan.sim_hour}: send ${fmtQty(first.qty, first.supply_id)} ${SUPPLY[first.supply_id].unit} ${first.supply_id} ${name(first.source_site_id)} → ${name(first.dest_site_id)}. ${plan.transfers.length} transfers, ${plan.scouts.length} scout visits. Full plan: ${url}`
    : `LANTERN: latest plan at ${url}`;

  return (
    <motion.div className="resilience" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <div className="res-left">
        <motion.div
          className="panel pad crt"
          initial={{ scaleY: 1, scaleX: 1, opacity: 1, filter: "brightness(1)" }}
          animate={{ scaleY: [1, 1, 0.012, 0.012], scaleX: [1, 1, 1, 0], opacity: [1, 1, 1, 0], filter: ["brightness(1)", "brightness(1)", "brightness(3)", "brightness(3)"] }}
          transition={{ duration: 1.6, times: [0, 0.45, 0.75, 1], ease: "easeIn", delay: 0.4 }}
        >
          <div className="row">
            <Power size={16} /> <b>Main dashboard + API</b>
          </div>
          <div className="tiny muted">Lambda · API Gateway · DynamoDB</div>
        </motion.div>
        <motion.div
          className="res-down"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 2.1, duration: 0.5 }}
        >
          <Power size={14} /> Main app offline
        </motion.div>
        <motion.div
          className="res-copy"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 2.5, duration: 0.6, ease: EASE }}
        >
          <h2>The plan still reaches the field.</h2>
          <p className="dim">
            Every approved plan is also published as a static page on S3 + CloudFront and sent by SNS text. No API, no
            database, no login needed.
          </p>
          <div className="sms-preview">
            <div className="sender">
              <MessageSquareText size={13} /> SMS · Amazon SNS
            </div>
            <div className="sms">{sms}</div>
          </div>
        </motion.div>
      </div>

      <motion.div
        className="phone"
        initial={{ opacity: 0, y: 40, rotate: 4 }}
        animate={{ opacity: 1, y: 0, rotate: 0 }}
        transition={{ delay: 2.8, type: "spring", stiffness: 140, damping: 18 }}
      >
        <div className="notch" />
        <iframe src="/fallback/" title="Static fallback page" />
      </motion.div>

      <motion.div
        className="panel pad qr"
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 3.4, duration: 0.5, ease: EASE }}
      >
        {qr ? <img src={qr} alt="QR code for the fallback page" /> : <div className="skel" />}
        <b>Open it on your phone</b>
        <span className="tiny muted mono">{url.replace(/^https?:\/\//, "")}</span>
        <div className="closing">
          <span className="lantern-mark">
            <Zap size={13} strokeWidth={2.6} />
          </span>
          Lantern · simulation only: the method, not a deployment
        </div>
      </motion.div>
    </motion.div>
  );
}
