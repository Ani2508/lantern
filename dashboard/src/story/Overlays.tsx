import { AnimatePresence, motion } from "motion/react";
import { Eye, X, Zap } from "lucide-react";
import { EASE } from "../lib/motion";
import { PERSONA } from "../lib/theme";
import { Typewriter } from "../components/ui";
import type { Beat } from "./beats";

export function Intro({ show, onStart }: { show: boolean; onStart: () => void }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          className="intro"
          onClick={onStart}
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, scale: 1.04, filter: "blur(6px)" }}
          transition={{ duration: 0.9, ease: EASE }}
        >
          <motion.div
            className="intro-glow"
            initial={{ opacity: 0, scale: 0.4 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 2.2, ease: EASE, delay: 0.3 }}
          />
          <motion.div
            className="intro-mark"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: [0, 1, 0.55, 1], scale: 1 }}
            transition={{ duration: 1.4, times: [0, 0.4, 0.55, 1], delay: 0.2 }}
          >
            <Zap size={42} strokeWidth={2.4} />
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.1, duration: 0.8, ease: EASE }}>
            Lantern
          </motion.h1>
          <motion.p
            className="intro-tag"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 1.6, duration: 0.8, ease: EASE }}
          >
            Supply planning that keeps working when the data goes dark.
          </motion.p>
          <motion.div className="intro-persona num" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 2.4 }}>
            <Typewriter text={`${PERSONA} · 08:00 · Fictional County`} cps={45} />
          </motion.div>
          <motion.div
            className="intro-go"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 1, 0.5, 1] }}
            transition={{ delay: 3.6, duration: 2, repeat: Infinity, repeatType: "reverse" }}
          >
            Press <kbd>Space</kbd> to begin
          </motion.div>
          <div className="intro-foot">SpartHill Hacks 2026 · AWS track · all data synthetic</div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Caption({ beat, index, total }: { beat: Beat; index: number; total: number }) {
  return (
    <AnimatePresence initial={false}>
      <motion.div
        key={beat.id}
        className="panel caption"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10, transition: { duration: 0.25 } }}
        transition={{ duration: 0.5, ease: EASE, delay: 0.15 }}
      >
        <div className="step">
          STEP {index} / {total} · {beat.short.toUpperCase()}
        </div>
        <h2>{beat.title}</h2>
        <p>{beat.caption}</p>
        {beat.notice && (
          <motion.div
            className="notice"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.9, duration: 0.4 }}
          >
            <Eye size={15} /> {beat.notice}
          </motion.div>
        )}
        {index <= 1 && (
          <div className="hint">
            <kbd>→</kbd> next · <kbd>←</kbd> back · <kbd>E</kbd> explore · <kbd>?</kbd> shortcuts
          </div>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

const KEYS: [string, string][] = [
  ["→ / Space / PgDn", "Next step"],
  ["← / PgUp", "Previous step"],
  ["R", "Restart from calm"],
  ["E", "Story ↔ Explore"],
  ["S", "Flip gate check (one at a time ↔ session)"],
  ["T", "Dark ↔ light theme"],
  ["F", "Fullscreen"],
  ["?", "This help"],
];

export function Help({ show, onClose }: { show: boolean; onClose: () => void }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div className="scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div
            className="panel pad help"
            initial={{ y: 20, scale: 0.97 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: 10, opacity: 0 }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="spread">
              <h3>Keyboard shortcuts</h3>
              <button className="btn icon ghost" onClick={onClose} aria-label="Close">
                <X size={16} />
              </button>
            </div>
            <table className="keys">
              <tbody>
                {KEYS.map(([k, v]) => (
                  <tr key={k}>
                    <td>
                      <kbd>{k}</kbd>
                    </td>
                    <td>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="tiny muted">Presentation clickers send PgDn/PgUp, so they work too. Add ?autoplay=1 to the URL to run the story on a timer.</p>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
