// The 7-step demo (contract 2.12, M5 doc 5.3). Captions double as the video's lower third.
import type { PlannerId, SupplyId } from "../api/types";

export interface StoryStep {
  n: number;
  title: string;
  caption: string;
  /** What the narrator says (a little fuller than the on-screen caption). */
  narration: string;
  speaker: string;
  hour: number;
  planner: PlannerId | null;
  supply: SupplyId | "all";
  overlay: "proof" | "resilience" | null;
  gate: boolean;
  dwellMs: number; // how long auto-play stays on this step
}

export const STORY: StoryStep[] = [
  {
    n: 1, title: "Calm", speaker: "M2", hour: 1, planner: null, supply: "all", overlay: null, gate: false, dwellMs: 6000,
    caption: "Five sites across the county, all reporting live. Every light on the map is a fresh count.",
    narration: "This is Riverbend County during a wildfire. Five supply sites, two shelters, a clinic, a pharmacy and a food bank, are all reporting live. Every blue light on the map is a fresh count.",
  },
  {
    n: 2, title: "Disaster", speaker: "M2", hour: 9, planner: null, supply: "all", overlay: null, gate: false, dwellMs: 7000,
    caption: "A wildfire starts. Two of five sites go dark, and their last numbers get older every hour.",
    narration: "The fire starts. Power and phone lines fail, and two of the five sites go silent. Their last numbers do not disappear. They just get older every hour, and Lantern shows that as fog that keeps growing.",
  },
  {
    n: 3, title: "Naive plan", speaker: "M2", hour: 9, planner: "naive", supply: "insulin", overlay: null, gate: false, dwellMs: 7000,
    caption: "A planner that trusts old data sees 40 vials at Central Pharmacy and starts moving them out.",
    narration: "Here is a typical planner that trusts old data. It still sees forty vials of insulin at Central Pharmacy, so it starts moving them out to the shelters. But that count is seven hours old.",
  },
  {
    n: 4, title: "Gate fires", speaker: "M4", hour: 9, planner: "naive", supply: "insulin", overlay: null, gate: true, dwellMs: 9000,
    caption: "Each transfer looked fine on its own. Together they break the pharmacy's insulin limit, on data 7 hours old. Blocked.",
    narration: "Lantern's safety gate checks the whole session, not one transfer at a time. Each move looked fine on its own. Together, they would break the pharmacy's insulin limit, on data seven hours old. So the gate blocks it.",
  },
  {
    n: 5, title: "Lantern plan", speaker: "M4", hour: 9, planner: "lantern", supply: "all", overlay: null, gate: false, dwellMs: 9000,
    caption: "Lantern plans for the low end of every range, moves only from sites it can see, and sends scouts where a fresh count changes the plan.",
    narration: "Lantern plans for the low end of every range. It only moves supplies from sites it can actually see, and it sends scouts to the two silent sites, where a fresh count would change the plan.",
  },
  {
    n: 6, title: "Proof", speaker: "M2", hour: 9, planner: "lantern", supply: "all", overlay: "proof", gate: false, dwellMs: 9000,
    caption: "As more sites go dark, shortages grow slowest with Lantern. Simulation only, measured across three hazards.",
    narration: "We tested this across three hazards and eight levels of data loss. As more sites go dark, shortages grow slowest with Lantern. These results come from simulation only.",
  },
  {
    n: 7, title: "Still works offline", speaker: "M4", hour: 9, planner: "lantern", supply: "all", overlay: "resilience", gate: false, dwellMs: 9000,
    caption: "Switch the main app off. The plan still reaches coordinators by text message and a static page.",
    narration: "And if the main app goes down, the plan still reaches coordinators, by text message, and by a simple static page that needs no app behind it.",
  },
];

export const EVENTS: { hour: number; label: string }[] = [
  { hour: 2, label: "Wildfire starts; Shelter B and Central Pharmacy go silent" },
  { hour: 3, label: "200 evacuees reach Shelter A" },
  { hour: 9, label: "Planning moment" },
];

/** First hour with silent sites in wildfire_demo_01 (fixture README). */
export const DARK_HOUR = 3;
