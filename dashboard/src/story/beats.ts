/** The demo story, one entry per keypress. Captions are what the room reads; the talk track is extras/demo_script.md. */
export type BeatId =
  | "intro"
  | "calm"
  | "disaster"
  | "naive"
  | "gate"
  | "lantern"
  | "field"
  | "recount"
  | "proof"
  | "resilience";

export type RailView = "sites" | "naive" | "gate" | "lantern" | "field" | "none";

export interface Beat {
  id: BeatId;
  short: string;
  title: string;
  caption: string;
  notice?: string;
  /** Site ids the camera frames; empty = all sites. */
  focus?: string[];
  rail: RailView;
}

export const BEATS: Beat[] = [
  {
    id: "intro",
    short: "Intro",
    title: "Lantern",
    caption: "Supply planning that keeps working when the data goes dark.",
    rail: "none",
  },
  {
    id: "calm",
    short: "Calm",
    title: "Five sites. Every count is live.",
    caption:
      "Maya coordinates water, food and insulin for two shelters, a clinic, a pharmacy and a food bank. Every site is reporting.",
    notice: "Blue beacons pulse while a site is reporting live.",
    rail: "sites",
  },
  {
    id: "disaster",
    short: "Wildfire",
    title: "A wildfire. Then the data goes dark.",
    caption:
      "At hour 2 a fire breaks out and two sites stop reporting. Their last counts get older every hour, and 200 evacuees arrive at Shelter A.",
    notice: "Dark sites turn grey and their uncertainty rings grow every hour.",
    rail: "sites",
  },
  {
    id: "naive",
    short: "Naive AI",
    title: "A planner that trusts old numbers",
    caption:
      "A naive AI planner still believes Central Pharmacy has 40 vials of insulin, its last count from 7 hours ago. It plans to pull insulin out of it, again and again.",
    notice: "Every arrow starts at the pharmacy that went dark.",
    focus: ["S04", "S01", "S02"],
    rail: "naive",
  },
  {
    id: "gate",
    short: "Gate fires",
    title: "The safety gate blocks it.",
    caption:
      "Each transfer looks fine on its own. Together they would leave the pharmacy below its insulin reserve, and its data is 7 hours old.",
    notice: "Flip the toggle: a one-at-a-time check lets all three through.",
    focus: ["S04", "S01", "S02"],
    rail: "gate",
  },
  {
    id: "lantern",
    short: "Lantern plan",
    title: "Lantern plans around what it doesn't know.",
    caption:
      "Lantern plans against the worst case, sources insulin from the clinic that is still reporting, and sends scouts where a count would change the plan.",
    notice: "Green flows pass every rule. Amber radar marks the scout visits.",
    rail: "lantern",
  },
  {
    id: "field",
    short: "Field report",
    title: "A scout texts in a count.",
    caption: "A volunteer at Central Pharmacy sends a plain-text message. The AI turns it into a structured count for Maya to confirm.",
    notice: "The model only reads the text. Maya confirms before anything changes.",
    focus: ["S04"],
    rail: "field",
  },
  {
    id: "recount",
    short: "Re-plan",
    title: "One count changes the plan.",
    caption:
      "The pharmacy comes back online. Its insulin range collapses from a wide guess to an exact 19 vials, and Lantern re-plans in milliseconds.",
    notice: "The pharmacy's ring snaps shut, and the arrows re-route.",
    rail: "lantern",
  },
  {
    id: "proof",
    short: "Proof",
    title: "Does it hold up?",
    caption: "We ran the same disaster across many synthetic worlds with more and more sites going dark.",
    rail: "none",
  },
  {
    id: "resilience",
    short: "Resilience",
    title: "Even if the dashboard goes down",
    caption: "The plan is also published as a static page and sent as a text. Scan to open it on your phone.",
    rail: "none",
  },
];

export const beatIndex = (id: BeatId) => BEATS.findIndex((b) => b.id === id);

export const SAMPLE_REPORT = "at central pharmacy now, counted 19 vials of insulin, fridge ok, line out the door";
