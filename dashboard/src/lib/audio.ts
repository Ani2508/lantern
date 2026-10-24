// Narration (the computer's built-in voices, Web Speech API) and small synthesized sound
// effects (Web Audio, no files). Both start off; browsers only allow sound after a click.

const PREFERRED = [
  "Ava (Premium)", "Ava (Enhanced)", "Zoe (Premium)", "Evan (Enhanced)", "Samantha",
  "Daniel", "Karen", "Google US English", "Microsoft Aria Online (Natural) - English (United States)", "Alex",
];

function pickVoice(): SpeechSynthesisVoice | null {
  if (!("speechSynthesis" in window)) return null;
  const voices = window.speechSynthesis.getVoices();
  const wanted = new URLSearchParams(window.location.search).get("voice");
  if (wanted) {
    const v = voices.find((x) => x.name.toLowerCase().includes(wanted.toLowerCase()));
    if (v) return v;
  }
  for (const name of PREFERRED) {
    const v = voices.find((x) => x.name === name);
    if (v) return v;
  }
  return voices.find((x) => x.lang?.startsWith("en")) ?? voices[0] ?? null;
}

export const narrator = {
  enabled: false,
  supported: typeof window !== "undefined" && "speechSynthesis" in window,
  voiceName: "",

  /** Speak text; resolves when finished, cancelled, or immediately when narration is off. */
  speak(text: string): Promise<void> {
    if (!this.enabled || !this.supported || !text) return Promise.resolve();
    const synth = window.speechSynthesis;
    synth.cancel();
    return new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      const v = pickVoice();
      if (v) {
        u.voice = v;
        this.voiceName = v.name;
      }
      u.rate = 0.97;
      u.pitch = 1;
      let done = false;
      const finish = () => {
        if (!done) {
          done = true;
          clearInterval(keepAlive);
          resolve();
        }
      };
      u.onend = finish;
      u.onerror = finish;
      // Safety net: never let a missing "end" event freeze the auto-play.
      const words = text.split(/\s+/).length;
      window.setTimeout(finish, words * 430 + 3500);
      // Chrome stops long utterances after ~15 s unless nudged.
      const keepAlive = window.setInterval(() => {
        if (!synth.speaking) return finish();
        synth.pause();
        synth.resume();
      }, 10000);
      synth.speak(u);
    });
  },

  cancel() {
    if (this.supported) window.speechSynthesis.cancel();
  },
};

// Voices load asynchronously in some browsers.
if (narrator.supported) window.speechSynthesis.onvoiceschanged = () => pickVoice();

let ctx: AudioContext | null = null;
function audio(): AudioContext | null {
  if (!sfx.enabled) return null;
  ctx ??= new AudioContext();
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

function tone(freq: number, start: number, dur: number, type: OscillatorType, gain: number, glideTo?: number) {
  const a = audio();
  if (!a) return;
  const t0 = a.currentTime + start;
  const osc = a.createOscillator();
  const g = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.03);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(a.destination);
  osc.start(t0);
  osc.stop(t0 + dur + 0.05);
}

export const sfx = {
  enabled: false,
  /** Sites go silent: a low falling tone. */
  dark() {
    tone(220, 0, 1.4, "sine", 0.12, 90);
    tone(330, 0.05, 1.2, "triangle", 0.04, 140);
  },
  /** The gate blocks: two short, soft alert tones. */
  alarm() {
    tone(660, 0, 0.22, "square", 0.05);
    tone(520, 0.28, 0.32, "square", 0.05);
  },
  /** A safe plan is ready: a gentle rising chime. */
  chime() {
    tone(523, 0, 0.6, "sine", 0.08);
    tone(659, 0.12, 0.6, "sine", 0.07);
    tone(784, 0.24, 0.9, "sine", 0.06);
  },
  /** The main app goes offline. */
  powerDown() {
    tone(400, 0, 0.9, "sawtooth", 0.035, 60);
  },
  /** A text message arrives. */
  ping() {
    tone(1318, 0, 0.18, "sine", 0.06);
    tone(1760, 0.1, 0.25, "sine", 0.05);
  },
};
